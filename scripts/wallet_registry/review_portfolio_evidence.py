"""Review public perpetual PnL histories. Never writes a live ranking or index."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

DAY_MS = 86_400_000


def points(raw):
    result = {}
    for timestamp, value in raw:
        number = float(value)
        if not math.isfinite(number) or int(timestamp) <= 0:
            raise ValueError('Invalid history point')
        if int(timestamp) in result and result[int(timestamp)] != number:
            raise ValueError('Conflicting history points')
        result[int(timestamp)] = number
    return sorted(result.items())


def window(raw):
    series = points(raw)
    if len(series) < 2:
        raise ValueError('Insufficient history')
    peak = series[0][1]
    max_drawdown = 0.0
    for _, pnl in series:
        peak = max(peak, pnl)
        max_drawdown = max(max_drawdown, peak - pnl)
    return {
        'start_ms': series[0][0], 'end_ms': series[-1][0],
        'coverage_days': (series[-1][0] - series[0][0]) / DAY_MS,
        'pnl_change_usd': series[-1][1] - series[0][1],
        'sampled_pnl_drawdown_usd': max_drawdown,
        'largest_sample_gap_hours': max(b[0] - a[0] for a, b in zip(series, series[1:])) / 3_600_000,
        'samples': len(series),
    }


def review(record, now):
    portfolio = dict(record['portfolio'])
    # Never mix total-account (spot + perp) history with perpetual-only equity.
    month = window(portfolio['perpMonth']['pnlHistory'])
    week = window(portfolio['perpWeek']['pnlHistory'])
    state = record['clearinghouseState']
    equity = float(state['marginSummary']['accountValue'])
    unrealized = sum(float(item['position']['unrealizedPnl']) for item in state['assetPositions'])
    issues = []
    for endpoint in ('portfolio', 'clearinghouseState'):
        stamp = dt.datetime.fromisoformat(record[endpoint + '_retrieved_at'])
        age = (now - stamp).total_seconds()
        if not 0 <= age <= 86400:
            issues.append(endpoint + '_stale')
    if month['coverage_days'] < 28:
        issues.append('short_month_history')
    history_age = now.timestamp() * 1000 - month['end_ms']
    if not -300_000 <= history_age <= DAY_MS:
        issues.append('stale_month_history')
    if not all(math.isfinite(v) for v in (equity, unrealized)):
        raise ValueError('Nonfinite account values')
    return {'address': record['address'], 'equity_usd': equity,
            'open_unrealized_pnl_usd': unrealized, 'month': month, 'week': week,
            'evidence_issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--active-wallets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    active = set(args.active_wallets.read_text().split())
    rows, errors = [], []
    now = dt.datetime.now(dt.timezone.utc)
    for path in sorted((args.evidence / 'wallets').glob('*.json')):
        try:
            rows.append(review(json.loads(path.read_text()), now))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({'file': path.name, 'error': str(exc)})
    current = [r for r in rows if r['address'] in active and not r['evidence_issues']]
    result = {'generated_at': now.isoformat(), 'review_only': True,
        'limitations': 'Returned PnL periods use their actual timestamps, not exact calendar months. Sampled dollar PnL drawdown is not percentage equity drawdown or an exact time-weighted return. Current open PnL is not added to historical PnL changes.',
        'active_expected': len(active), 'active_validated': len(current),
        'active_negative_month': sum(r['month']['pnl_change_usd'] < 0 for r in current),
        'active_month_pnl_change_usd': sum(r['month']['pnl_change_usd'] for r in current),
        'active_open_pnl_usd': sum(r['open_unrealized_pnl_usd'] for r in current),
        'wallets': rows, 'errors': errors}
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ('wallets', 'errors')}, indent=2))


if __name__ == '__main__':
    main()

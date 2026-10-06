"""Shadow ranking using observed perpetual PnL, never profit/current balance.

This deliberately has no live-write or reset option. Activation requires a fresh
metrics scan and a separately validated, versioned index transition.
"""
import datetime as dt

from review_portfolio_evidence import DAY_MS, points, review, window

METHOD = 'copycat_perpetual_profit_shadow_v4'


def evidence_metrics(record, now):
    result = review(record, now)
    if result['evidence_issues']:
        raise ValueError(','.join(result['evidence_issues']))
    portfolio = dict(record['portfolio'])
    history = points(portfolio['perpAllTime']['pnlHistory'])
    end = history[-1][0]
    cutoff = end - 90 * DAY_MS
    preceding = [p for p in history if p[0] <= cutoff]
    if not preceding:
        raise ValueError('Need at least 90 days of observed perpetual history')
    start = preceding[-1]
    long_history = [p for p in history if p[0] >= start[0]]
    long_window = window(long_history)
    # Preserve actual timestamps; do not fabricate a 90-day point by interpolation.
    if long_window['coverage_days'] > 98 or long_window['largest_sample_gap_hours'] > 8 * 24:
        raise ValueError('Long-term history too sparse')
    if abs(end - result['month']['end_ms']) > DAY_MS:
        raise ValueError('History endpoints disagree')
    if result['equity_usd'] < 5000:
        raise ValueError('Equity below minimum')
    if long_window['pnl_change_usd'] <= 0 or result['month']['pnl_change_usd'] <= 0:
        raise ValueError('Nonpositive recent or long-term perpetual PnL')
    deltas = [b[1] - a[1] for a, b in zip(long_history, long_history[1:])]
    gains = sum(max(0, value) for value in deltas)
    concentration = max(deltas) / gains if gains else 1.0
    consistency = sum(value > 0 for value in deltas) / len(deltas)
    pnl = long_window['pnl_change_usd']
    # Bounded sampled profit-versus-drawdown quality, not equity drawdown or Sharpe.
    recovery = pnl / (pnl + long_window['sampled_pnl_drawdown_usd'])
    return {**result, 'long_window': long_window,
            'positive_sample_interval_ratio': consistency,
            'largest_positive_interval_share': concentration,
            'sampled_recovery_quality': recovery}


def percentiles(values):
    ordered = sorted(values.values())
    if len(ordered) <= 1:
        return {key: 0.5 for key in values}
    # Midrank ties receive the same neutral percentile, including an all-tied set.
    return {key: (sum(v < value for v in ordered) + (sum(v == value for v in ordered) - 1) / 2)
            / (len(ordered) - 1) for key, value in values.items()}


def rank_evidence(records, now=None, selection_limit=50):
    now = now or dt.datetime.now(dt.timezone.utc)
    eligible, excluded = [], []
    seen = set()
    for record in records:
        address = record.get('address')
        if address in seen:
            raise ValueError('Duplicate wallet evidence')
        seen.add(address)
        try:
            eligible.append(evidence_metrics(record, now))
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            excluded.append({'address': address, 'reason': str(exc)})
    # Compare profit per actual covered day across unequal returned windows.
    long_pct = percentiles({r['address']: r['long_window']['pnl_change_usd'] / r['long_window']['coverage_days'] for r in eligible})
    month_pct = percentiles({r['address']: r['month']['pnl_change_usd'] / r['month']['coverage_days'] for r in eligible})
    for row in eligible:
        address = row['address']
        row['score'] = round(35 * long_pct[address] + 25 * month_pct[address]
            + 20 * row['positive_sample_interval_ratio']
            + 15 * row['sampled_recovery_quality']
            + 5 * (1 - row['largest_positive_interval_share']), 6)
    eligible.sort(key=lambda r: (-r['score'], r['address']))
    return {'method': METHOD, 'shadow_only': True, 'eligible': len(eligible),
            'selected': eligible[:selection_limit], 'excluded': excluded,
            'can_activate': False,
            'note': 'Research ranking only. Requires independent fresh trade-history qualification before live selection. Dollar profitability rewards larger profitable accounts; this is not a capital-return ranking. Sampled drawdowns understate losses between observations.'}


def rank_qualified(metrics, evidence, now):
    """Join fresh independently qualified trade records to portfolio evidence.

    Evidence-only research results cannot enter this production-ready report.
    The caller remains responsible for the legacy minimum activity/history gates.
    """
    fresh = {}
    for row in metrics:
        observed = dt.datetime.fromisoformat(row['observed_at_utc'].replace('Z', '+00:00'))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=dt.timezone.utc)
        if 0 <= (now - observed).total_seconds() <= 86400:
            fresh[row['address']] = row
    result = rank_evidence([r for r in evidence if r.get('address') in fresh], now, selection_limit=None)
    ranked = []
    for rank_number, row in enumerate(result['selected'], 1):
        original = fresh[row['address']]
        ranked.append({**original, 'consistency_score': row['score'],
            'profit_factor': float(original.get('gross_profit', 0)) / max(float(original.get('gross_loss', 0)), 1),
            'universe_rank': rank_number, 'roi': None, 'performance_evidence': row})
    return ranked, {'portfolio_or_freshness_excluded': len(metrics) - len(ranked)}

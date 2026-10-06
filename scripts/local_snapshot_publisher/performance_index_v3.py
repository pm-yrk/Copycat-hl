"""Isolated index engine. Existing production series are never opened or reset.

The model caps each wallet's gross notional at its equity, gives each tracked
wallet an equal budget, nets opposing positions and retains unused collateral.
It charges the existing 15bp turnover buffer. Funding is not modelled here.
"""
import json
import math
from pathlib import Path
import re
import sqlite3
import datetime as dt

METHOD = 'copycat_equal_wallet_net_exposure_v3'
FEE_RATE = 0.0015
ASSET_CAP = 0.25


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Nonfinite index input')
    return result


def build_targets(states, wallets, stablecoins):
    wallets = [str(a).lower() for a in wallets]
    if len(wallets) != 50 or len(set(wallets)) != 50:
        raise ValueError('Index requires exactly 50 unique wallets')
    by_wallet = {str(s.get('_wallet', '')).lower(): s for s in states}
    if len(states) != 50 or set(by_wallet) != set(wallets):
        raise ValueError('Incomplete or duplicate wallet states')
    net, counts = {}, {}
    for wallet in wallets:
        state = by_wallet[wallet]
        if state.get('_copycat_state_status') != 'live':
            raise ValueError('Stale wallet state cannot rebalance the index')
        equity = number(state['marginSummary']['accountValue'])
        if equity <= 0:
            raise ValueError('Nonpositive wallet equity')
        positions = {}
        for item in state['assetPositions']:
            pos = item['position']
            coin = str(pos['coin'])
            size = number(pos['szi'])
            if coin.upper() in stablecoins or size == 0:
                continue
            value = abs(number(pos['positionValue']))
            if value <= 0 or coin in positions:
                raise ValueError('Invalid or duplicate position')
            positions[coin] = value if size > 0 else -value
        # Scale the entire wallet book proportionally; do not clip each asset
        # first, which changes relative conviction in leveraged portfolios.
        denominator = max(equity, sum(abs(v) for v in positions.values()))
        for coin, value in positions.items():
            net[coin] = net.get(coin, 0) + value / denominator / 50
            sides = counts.setdefault(coin, {'long': 0, 'short': 0})
            sides['long' if value > 0 else 'short'] += 1
    result = []
    for coin, value in net.items():
        weight = max(-ASSET_CAP, min(ASSET_CAP, value))
        if abs(weight) < 1e-12:
            continue
        result.append({'coin': coin, 'signed_weight': weight, 'index_weight': weight,
            'target_weight': abs(weight), 'direction': 'long' if weight > 0 else 'short',
            'wallets_long': counts[coin]['long'], 'wallets_short': counts[coin]['short'],
            'participating_wallets': sum(counts[coin].values()), 'allocation_method': METHOD})
    return sorted(result, key=lambda r: (-r['target_weight'], r['coin']))


def weights_from_targets(targets):
    weights = {}
    for row in targets:
        coin = row['coin']
        if coin in weights:
            raise ValueError('Duplicate target')
        weights[coin] = number(row['signed_weight'])
        if abs(weights[coin]) > ASSET_CAP + 1e-10:
            raise ValueError('Asset cap exceeded')
    if sum(abs(v) for v in weights.values()) > 1 + 1e-10:
        raise ValueError('Gross exposure exceeds equity')
    return weights


def display_targets(targets, now_ms):
    """Keep existing allocation renderers from magnifying net exposure to 100%."""
    weights = weights_from_targets(targets)
    reserve = max(0, 1 - sum(abs(v) for v in weights.values()))
    rows = [dict(r) for r in targets]
    if reserve > 1e-10:
        rows.append({'coin': 'UNALLOCATED', 'target_weight': reserve,
            'signed_weight': 0, 'index_weight': 0, 'direction': 'reserve',
            'ts_ms': now_ms, 'is_collateral': True, 'allocation_method': METHOD,
            'note': 'Unallocated model collateral, not observed USDC wallet holdings.'})
    return rows


def advance(state, now_ms, targets, prices):
    """Pure mark/rebalance step; raises before any write on invalid prices."""
    now_ms = int(now_ms)
    if now_ms <= 0:
        raise ValueError('Invalid observation time')
    weights = weights_from_targets(targets)
    if state and now_ms <= state['latest_ts_ms']:
        if now_ms == state['latest_ts_ms']:
            return state  # Retry is idempotent, including transaction costs.
        raise ValueError('Out-of-order observation')
    old_units = state.get('units', {}) if state else {}
    required = set(weights) | set(old_units) | {'BTC', 'ETH', 'xyz:SP500'}
    marks = {coin: number(prices[coin]) for coin in required}
    if any(value <= 0 for value in marks.values()):
        raise ValueError('Missing or nonpositive mark')
    if not state:
        # Inception is normalised after initial setup; subsequent turnover costs
        # are charged. A restart loads this state rather than normalising again.
        nav, cost, turnover = 100.0, 0.0, 0.0
        starts = {c: marks[c] for c in ('BTC', 'ETH', 'xyz:SP500')}
        first = now_ms
        max_dd, peak = 0.0, 100.0
    else:
        marked = state['copycat_nav'] + sum(units * (marks[c] - state['last_mids'][c])
                                           for c, units in old_units.items())
        if marked <= 0:
            raise ValueError('Model insolvent; manual review required')
        marked_positions = {c: u * marks[c] for c, u in old_units.items()}
        # Solve cost = rate * traded dollars using post-cost target NAV.
        lo, hi = 0.0, marked
        for _ in range(60):
            cost = (lo + hi) / 2
            turnover = sum(abs(weights.get(c, 0) * (marked - cost) - marked_positions.get(c, 0))
                           for c in set(weights) | set(marked_positions))
            if cost > FEE_RATE * turnover:
                hi = cost
            else:
                lo = cost
        cost = (lo + hi) / 2
        nav = marked - cost
        first, starts = state['start_ts_ms'], state['benchmark_start_prices']
        peak = max(state['peak_nav'], nav)
        max_dd = min(state['max_drawdown_pct'], (nav / peak - 1) * 100)
    return {'method_version': METHOD, 'start_ts_ms': first, 'latest_ts_ms': now_ms,
        'copycat_nav': nav, 'units': {c: weights[c] * nav / marks[c] for c in weights},
        'last_mids': marks, 'current_weights': targets, 'benchmark_start_prices': starts,
        'btc_nav': 100 * marks['BTC'] / starts['BTC'],
        'eth_nav': 100 * marks['ETH'] / starts['ETH'],
        'spx_nav': 100 * marks['xyz:SP500'] / starts['xyz:SP500'],
        'peak_nav': peak, 'max_drawdown_pct': max_dd,
        'fee_slippage_cost_usd': cost, 'turnover_usd': turnover,
        'fee_slippage_rate': FEE_RATE, 'funding_included': False,
        'unallocated_collateral_weight': max(0, 1 - sum(abs(v) for v in weights.values())),
        'observation_gap_ms': now_ms - state['latest_ts_ms'] if state else 0}


def record(root, series_id, now_ms, targets, prices):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', series_id):
        raise ValueError('Invalid series identifier')
    path = Path(root) / series_id / 'index.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    try:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=FULL')
        con.execute('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), json TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS points(ts_ms INTEGER PRIMARY KEY, json TEXT NOT NULL)')
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT json FROM state WHERE id=1').fetchone()
        if row is None and con.execute('SELECT 1 FROM points LIMIT 1').fetchone():
            raise ValueError('State missing from existing series; refusing implicit reset')
        state = json.loads(row[0]) if row else None
        if state and state.get('method_version') != METHOD:
            raise ValueError('Cannot mix index methodologies')
        updated = advance(state, now_ms, targets, prices)
        updated['series_id'] = series_id
        payload = json.dumps(updated, allow_nan=False)
        point = {k: updated[k] for k in ('latest_ts_ms', 'copycat_nav', 'btc_nav', 'eth_nav',
                 'spx_nav', 'max_drawdown_pct', 'fee_slippage_cost_usd', 'turnover_usd')}
        con.execute('INSERT OR REPLACE INTO points VALUES (?, ?)', (now_ms, json.dumps(point)))
        con.execute('INSERT OR REPLACE INTO state VALUES (1, ?)', (payload,))
        con.commit()
        return updated
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def public_snapshot(root, state):
    """Bounded chart reads; performance/drawdown remain based on full observations."""
    now = state['latest_ts_ms']
    day = 86_400_000
    start = state['start_ts_ms']
    year = dt.datetime.fromtimestamp(now / 1000, dt.timezone.utc).year
    ytd = int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    windows = {'1D': now-day, '1W': now-7*day, '1M': now-30*day,
               'YTD': ytd, '1Y': now-365*day, 'ALL': start}
    def point(raw):
        value = json.loads(raw)
        return {'ts_ms': value['latest_ts_ms'], 'live': True,
                **{k: value[k] for k in ('copycat_nav', 'btc_nav', 'eth_nav', 'spx_nav')},
                **{k+'_return_pct': value[k+'_nav']-100 for k in ('copycat', 'btc', 'eth', 'spx')}}
    timeframes = {}
    with sqlite3.connect(Path(root) / state['series_id'] / 'index.sqlite') as con:
        for label, cutoff in windows.items():
            cutoff = max(start, cutoff)
            bucket = max(1, math.ceil((now - cutoff + 1) / 450))
            rows = con.execute('''SELECT p.json FROM points p JOIN
                (SELECT MAX(ts_ms) AS ts FROM points WHERE ts_ms>=? GROUP BY CAST(ts_ms / ? AS INTEGER)) b
                ON p.ts_ms=b.ts ORDER BY p.ts_ms''', (cutoff, bucket)).fetchall()
            first = con.execute('SELECT json FROM points WHERE ts_ms>=? ORDER BY ts_ms LIMIT 1', (cutoff,)).fetchone()
            converted = [point(r[0]) for r in rows]
            if first:
                converted.insert(0, point(first[0]))
            timeframes[label] = list({p['ts_ms']: p for p in converted}.values())
    merged = {p['ts_ms']: p for series in timeframes.values() for p in series}
    return {'status': 'ok', 'source': 'local_snapshot_index_v3', 'method': METHOD,
        'series_id': state['series_id'], 'start_ts_ms': start, 'latest_ts_ms': now,
        'method_note': 'Equal wallet budgets; gross exposure capped at equity; opposing positions netted; '
            '25% asset cap; unused collateral retained. Inception normalised to 100 after setup. '
            '15bp turnover buffer applied thereafter; funding excluded. Positions held until the next complete observation.',
        **{k: state[k] for k in ('copycat_nav', 'btc_nav', 'eth_nav', 'spx_nav', 'max_drawdown_pct',
            'fee_slippage_rate', 'funding_included', 'unallocated_collateral_weight', 'observation_gap_ms')},
        **{k+'_return_pct': state[k+'_nav']-100 for k in ('copycat', 'btc', 'eth', 'spx')},
        'current_weights': [{**r, 'weight': abs(r['signed_weight'])} for r in state['current_weights']],
        'points': [merged[t] for t in sorted(merged)], 'points_count': len(merged), 'timeframes': timeframes,
        'previous_period_weights_used': True, 'snapshot_mode': True, 'public_readonly': True,
        'spx_benchmark_symbol': 'xyz:SP500'}

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

import stripe
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .auth import get_current_user, require_active_subscription
from .db import fetch_all, fetch_one, execute, engine
from .settings import get_settings

settings = get_settings()
stripe.api_key = settings.stripe_secret_key or None

app = FastAPI(title='Hyper Wallet Tracker SaaS API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_site_url, 'http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    row = fetch_one('SELECT now() AS now')
    return {'status': 'ok', 'database': bool(row)}


@app.get('/api/me')
def me(user: dict = Depends(get_current_user)):
    return user


@app.get('/api/summary')
def summary(user: dict = Depends(require_active_subscription)):
    latest_signal = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    stable_ts = latest_signal.get('ts_ms')
    latest_wallets = fetch_one("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'") or {'n': 0}

    if stable_ts:
        signal_rollup = fetch_one(
            """
            SELECT
              COALESCE(max(total_tracked_value_usd),0) AS tracked_total,
              COALESCE(sum(value_long_usd + value_short_usd),0) AS signal_open_total,
              COALESCE(sum(wallets_long + wallets_short),0) AS signal_positions,
              count(*) AS assets
            FROM asset_signals
            WHERE ts_ms=:ts
            """,
            {'ts': stable_ts},
        ) or {'tracked_total': 0, 'signal_open_total': 0, 'signal_positions': 0, 'assets': 0}
        snapshot_rollup = fetch_one(
            """
            SELECT COALESCE(sum(ws.account_value_usd),0) AS tracked_total, count(DISTINCT ws.wallet) AS wallets
            FROM wallet_snapshots ws
            JOIN qualified_wallets q ON q.wallet=ws.wallet AND q.status='active'
            WHERE ws.ts_ms=:ts
            """,
            {'ts': stable_ts},
        ) or {'tracked_total': 0, 'wallets': 0}
        position_rollup = fetch_one(
            """
            SELECT COALESCE(sum(p.position_value_usd),0) AS open_total, count(*) AS positions
            FROM positions p
            JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            WHERE p.ts_ms=:ts
            """,
            {'ts': stable_ts},
        ) or {'open_total': 0, 'positions': 0}

        # Account value and open-position value come from the same completed
        # collection timestamp as the signal board. Signals are only for assets
        # that pass the signal filters, so the headline open-position value must
        # use the raw positions table instead of summing only signal rows.
        tracked_total = snapshot_rollup['tracked_total'] if int(snapshot_rollup.get('wallets') or 0) > 0 else signal_rollup['tracked_total']
        open_total = position_rollup['open_total'] if int(position_rollup.get('positions') or 0) > 0 else signal_rollup['signal_open_total']
        open_positions = position_rollup['positions'] if int(position_rollup.get('positions') or 0) > 0 else signal_rollup['signal_positions']
        assets = {'n': signal_rollup['assets']}
        total_value = {'total': tracked_total}
        open_value = {'total': open_total, 'positions': open_positions}
    else:
        total_value = fetch_one(
            """
            WITH latest AS (
              SELECT DISTINCT ON (wallet) wallet, account_value_usd
              FROM wallet_snapshots ORDER BY wallet, ts_ms DESC
            ) SELECT COALESCE(sum(account_value_usd),0) AS total FROM latest
            """
        ) or {'total': 0}
        open_value = fetch_one(
            """
            WITH latest_ts AS (SELECT max(ts_ms) ts_ms FROM positions)
            SELECT COALESCE(sum(p.position_value_usd),0) AS total, count(*) AS positions
            FROM positions p
            JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            WHERE p.ts_ms=(SELECT ts_ms FROM latest_ts)
            """
        ) or {'total': 0, 'positions': 0}
        assets = {'n': 0}

    latest_pos_ts = fetch_one('SELECT max(ts_ms) AS ts_ms FROM positions') or {'ts_ms': None}
    return {
        'latest_signal_ts_ms': stable_ts,
        'latest_position_ts_ms': latest_pos_ts['ts_ms'],
        'qualified_wallets': latest_wallets['n'],
        'tracked_account_value_usd': float(total_value['total'] or 0),
        'tracked_open_position_value_usd': float(open_value['total'] or 0),
        'open_positions': int(open_value['positions'] or 0),
        'assets_with_signals': assets['n'],
    }


@app.get('/api/data-health')
def data_health(user: dict = Depends(require_active_subscription)):
    latest_signal = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    latest_position = fetch_one('SELECT max(ts_ms) AS ts_ms FROM positions') or {'ts_ms': None}
    ts = latest_signal.get('ts_ms')
    signal_rollup = {'tracked_total': 0, 'open_total': 0, 'open_positions': 0, 'assets': 0}
    positions_at_signal = {'open_total': 0, 'open_positions': 0}
    latest_positions = {'open_total': 0, 'open_positions': 0}
    if ts:
        signal_rollup = fetch_one(
            """
            SELECT COALESCE(max(total_tracked_value_usd),0) AS tracked_total,
                   COALESCE(sum(value_long_usd + value_short_usd),0) AS open_total,
                   COALESCE(sum(wallets_long + wallets_short),0) AS open_positions,
                   count(*) AS assets
            FROM asset_signals WHERE ts_ms=:ts
            """, {'ts': ts}
        ) or signal_rollup
        positions_at_signal = fetch_one(
            """
            SELECT COALESCE(sum(p.position_value_usd),0) AS open_total, count(*) AS open_positions
            FROM positions p
            JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            WHERE p.ts_ms=:ts
            """, {'ts': ts}
        ) or positions_at_signal
    latest_positions = fetch_one(
        """
        WITH latest_ts AS (SELECT max(ts_ms) ts_ms FROM positions)
        SELECT COALESCE(sum(p.position_value_usd),0) AS open_total, count(*) AS open_positions
        FROM positions p
        JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
        WHERE p.ts_ms=(SELECT ts_ms FROM latest_ts)
        """
    ) or latest_positions
    latest_run = fetch_one('SELECT * FROM collector_runs ORDER BY ts_ms DESC LIMIT 1') or {}
    return {
        'latest_signal_ts_ms': ts,
        'latest_position_ts_ms': latest_position.get('ts_ms'),
        'signal_rollup': {k: float(v or 0) if k != 'assets' else int(v or 0) for k, v in dict(signal_rollup).items()},
        'positions_at_signal_ts': {k: float(v or 0) for k, v in dict(positions_at_signal).items()},
        'latest_positions': {k: float(v or 0) for k, v in dict(latest_positions).items()},
        'latest_run': latest_run,
        'summary_source': 'asset_signals_latest_completed_snapshot',
    }


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _now_ms() -> int:
    return int(time.time() * 1000)


def _within_tolerance(a: float, b: float, pct: float = 0.0075, abs_tol: float = 5000.0) -> bool:
    a = _safe_float(a); b = _safe_float(b)
    return abs(a - b) <= max(abs_tol, pct * max(abs(a), abs(b), 1.0))


def _delta_metrics(a: float, b: float) -> dict[str, float]:
    a = _safe_float(a); b = _safe_float(b)
    return {
        'a': a,
        'b': b,
        'delta': a - b,
        'delta_abs': abs(a - b),
        'delta_pct': (abs(a - b) / max(abs(a), abs(b), 1.0)) * 100.0,
    }


def _add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str = '', severity: str = 'error', metrics: dict[str, Any] | None = None):
    checks.append({
        'name': name,
        'status': 'pass' if ok else 'fail',
        'severity': severity,
        'detail': detail,
        'metrics': metrics or {},
    })


def _in_clause(name: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    params = {f'{name}{i}': v for i, v in enumerate(values)}
    return ','.join(f':{name}{i}' for i in range(len(values))), params


def _hl_info(payload: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        settings.hl_info_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'CopycatAudit/1.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode('utf-8'))


def _live_wallet_totals(wallets: list[str]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        'wallets_requested': len(wallets),
        'wallets_ok': 0,
        'errors': [],
        'account_value_usd': 0.0,
        'open_position_value_usd': 0.0,
        'open_positions': 0,
        'by_asset': {},
    }
    for wallet in wallets:
        try:
            state = _hl_info({'type': 'clearinghouseState', 'user': wallet})
            ms = state.get('marginSummary') or state.get('crossMarginSummary') or {}
            totals['account_value_usd'] += _safe_float(ms.get('accountValue'))
            for item in state.get('assetPositions') or []:
                p = item.get('position') if isinstance(item, dict) else None
                p = p or item
                if not isinstance(p, dict):
                    continue
                coin = str(p.get('coin') or '').upper()
                szi = _safe_float(p.get('szi'))
                value = abs(_safe_float(p.get('positionValue')))
                if not coin or value <= 0 or szi == 0:
                    continue
                side = 'long' if szi > 0 else 'short'
                bucket = totals['by_asset'].setdefault(coin, {'value_long_usd': 0.0, 'value_short_usd': 0.0, 'wallets_long': 0, 'wallets_short': 0})
                if side == 'long':
                    bucket['value_long_usd'] += value; bucket['wallets_long'] += 1
                else:
                    bucket['value_short_usd'] += value; bucket['wallets_short'] += 1
                totals['open_position_value_usd'] += value
                totals['open_positions'] += 1
            totals['wallets_ok'] += 1
            time.sleep(0.08)
        except Exception as exc:
            totals['errors'].append({'wallet': wallet, 'error': str(exc)[:220]})
    return totals


def _db_wallet_subset_totals(wallets: list[str], ts: int | None) -> dict[str, Any]:
    if not wallets or not ts:
        return {'wallets': 0, 'account_value_usd': 0.0, 'open_position_value_usd': 0.0, 'open_positions': 0, 'by_asset': {}}
    in_sql, params = _in_clause('w', wallets)
    params['ts'] = ts
    snap = fetch_one(
        f"""
        WITH latest AS (
          SELECT DISTINCT ON (wallet) wallet, account_value_usd
          FROM wallet_snapshots
          WHERE wallet IN ({in_sql}) AND ts_ms <= :ts
          ORDER BY wallet, ts_ms DESC
        )
        SELECT count(*) AS wallets, COALESCE(sum(account_value_usd),0) AS account_value_usd
        FROM latest
        """,
        params,
    ) or {'wallets': 0, 'account_value_usd': 0}
    pos = fetch_one(
        f"""
        SELECT count(*) AS open_positions, COALESCE(sum(position_value_usd),0) AS open_position_value_usd
        FROM positions
        WHERE ts_ms=:ts AND wallet IN ({in_sql})
        """,
        params,
    ) or {'open_positions': 0, 'open_position_value_usd': 0}
    by_asset_rows = fetch_all(
        f"""
        SELECT coin,
               COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='long'),0) AS value_long_usd,
               COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='short'),0) AS value_short_usd,
               count(*) FILTER (WHERE lower(side)='long') AS wallets_long,
               count(*) FILTER (WHERE lower(side)='short') AS wallets_short
        FROM positions
        WHERE ts_ms=:ts AND wallet IN ({in_sql})
        GROUP BY coin
        """,
        params,
    )
    return {
        'wallets': int(snap.get('wallets') or 0),
        'account_value_usd': float(snap.get('account_value_usd') or 0),
        'open_position_value_usd': float(pos.get('open_position_value_usd') or 0),
        'open_positions': int(pos.get('open_positions') or 0),
        'by_asset': {str(r['coin']).upper(): dict(r) for r in by_asset_rows},
    }


@app.get('/api/audit')
def audit(live: bool = False, full: bool = False, max_wallets: int = 10, user: dict = Depends(require_active_subscription)):
    checks: list[dict[str, Any]] = []
    now = _now_ms()
    max_wallets = max(1, min(50, int(max_wallets or 10)))
    latest_signal = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    ts = latest_signal.get('ts_ms')
    active_wallets = fetch_all("SELECT wallet, rank FROM qualified_wallets WHERE status='active' ORDER BY rank")
    wallet_list = [r['wallet'] for r in active_wallets]

    signal_rollup = {'tracked_total': 0, 'signal_open_total': 0, 'signal_positions': 0, 'assets': 0, 'bullish_flow': 0, 'bearish_flow': 0, 'net_abs_flow': 0}
    snapshot_rollup = {'tracked_total': 0, 'wallets': 0}
    position_rollup = {'open_total': 0, 'positions': 0, 'coins': 0, 'wallets': 0}
    target_rollup = {'target_sum': 0, 'targets': 0}
    collector = fetch_one('SELECT * FROM collector_runs ORDER BY ts_ms DESC LIMIT 1') or {}
    stale_seconds = None

    if ts:
        signal_rollup = fetch_one(
            """
            SELECT COALESCE(max(total_tracked_value_usd),0) AS tracked_total,
                   COALESCE(sum(value_long_usd + value_short_usd),0) AS signal_open_total,
                   COALESCE(sum(wallets_long + wallets_short),0) AS signal_positions,
                   count(*) AS assets,
                   COALESCE(sum(bullish_value_flow_usd),0) AS bullish_flow,
                   COALESCE(sum(bearish_value_flow_usd),0) AS bearish_flow,
                   COALESCE(sum(abs(net_value_flow_usd)),0) AS net_abs_flow
            FROM asset_signals WHERE ts_ms=:ts
            """,
            {'ts': ts},
        ) or signal_rollup
        snapshot_rollup = fetch_one(
            """
            SELECT COALESCE(sum(ws.account_value_usd),0) AS tracked_total, count(DISTINCT ws.wallet) AS wallets
            FROM wallet_snapshots ws
            JOIN qualified_wallets q ON q.wallet=ws.wallet AND q.status='active'
            WHERE ws.ts_ms=:ts
            """,
            {'ts': ts},
        ) or snapshot_rollup
        position_rollup = fetch_one(
            """
            SELECT COALESCE(sum(p.position_value_usd),0) AS open_total,
                   count(*) AS positions,
                   count(DISTINCT p.coin) AS coins,
                   count(DISTINCT p.wallet) AS wallets
            FROM positions p
            JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
            WHERE p.ts_ms=:ts
            """,
            {'ts': ts},
        ) or position_rollup
        target_rollup = fetch_one(
            """
            WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM portfolio_targets)
            SELECT COALESCE(sum(target_weight),0) AS target_sum, count(*) AS targets
            FROM portfolio_targets WHERE ts_ms=(SELECT ts_ms FROM latest)
            """
        ) or target_rollup

    if collector.get('ts_ms'):
        stale_seconds = max(0, (now - int(collector['ts_ms'])) / 1000.0)

    _add_check(checks, 'Active wallet cohort', len(wallet_list) == 50, f'{len(wallet_list)} active wallets selected', 'warning' if len(wallet_list) > 0 else 'error')
    _add_check(checks, 'Completed signal snapshot exists', bool(ts), f'latest signal ts={ts}')
    _add_check(checks, 'Collector freshness', stale_seconds is not None and stale_seconds <= 45, f'last collector run {stale_seconds:.1f}s ago' if stale_seconds is not None else 'no collector run found', 'warning')
    _add_check(checks, 'Positions exist at signal timestamp', int(position_rollup.get('positions') or 0) > 0, f"{position_rollup.get('positions',0)} positions at latest signal timestamp")
    _add_check(checks, 'Snapshot wallet count matches cohort', int(snapshot_rollup.get('wallets') or 0) >= max(1, len(wallet_list) - 2), f"{snapshot_rollup.get('wallets',0)} wallet snapshots at latest timestamp", 'warning')
    _add_check(checks, 'Tracked account value consistency', _within_tolerance(snapshot_rollup.get('tracked_total'), signal_rollup.get('tracked_total'), pct=0.005, abs_tol=25000), 'wallet snapshots vs signal rollup', metrics=_delta_metrics(snapshot_rollup.get('tracked_total'), signal_rollup.get('tracked_total')))
    _add_check(checks, 'Open position value non-zero when signals have exposure', not (_safe_float(position_rollup.get('open_total')) == 0 and _safe_float(signal_rollup.get('signal_open_total')) > 0), 'positions table vs signal exposure', metrics={'positions_open_total': float(position_rollup.get('open_total') or 0), 'signal_open_total': float(signal_rollup.get('signal_open_total') or 0)})
    target_sum = _safe_float(target_rollup.get('target_sum'))
    _add_check(checks, 'Portfolio targets sum to 100%', 0.995 <= target_sum <= 1.005, f'target sum={target_sum:.6f}', metrics=dict(target_rollup))

    bad_flow = fetch_one(
        """
        WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT count(*) AS n FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest)
          AND abs(net_value_flow_usd) > 1000
          AND COALESCE(bullish_value_flow_usd,0)=0
          AND COALESCE(bearish_value_flow_usd,0)=0
        """
    ) or {'n': 0}
    _add_check(checks, 'Buyer/seller flow fields populated', int(bad_flow.get('n') or 0) == 0, f"{bad_flow.get('n',0)} rows have net flow but zero bullish/bearish flow")

    mismatches = []
    if ts:
        asset_compare = fetch_all(
            """
            WITH pos AS (
              SELECT coin,
                     COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='long'),0) AS pos_long,
                     COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='short'),0) AS pos_short,
                     count(*) FILTER (WHERE lower(side)='long') AS pos_wallets_long,
                     count(*) FILTER (WHERE lower(side)='short') AS pos_wallets_short
              FROM positions p
              JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
              WHERE p.ts_ms=:ts GROUP BY p.coin
            )
            SELECT s.coin, s.value_long_usd AS signal_long, s.value_short_usd AS signal_short,
                   s.wallets_long AS signal_wallets_long, s.wallets_short AS signal_wallets_short,
                   COALESCE(p.pos_long,0) AS pos_long, COALESCE(p.pos_short,0) AS pos_short,
                   COALESCE(p.pos_wallets_long,0) AS pos_wallets_long, COALESCE(p.pos_wallets_short,0) AS pos_wallets_short
            FROM asset_signals s
            LEFT JOIN pos p ON upper(p.coin)=upper(s.coin)
            WHERE s.ts_ms=:ts
            ORDER BY abs((s.value_long_usd+s.value_short_usd) - (COALESCE(p.pos_long,0)+COALESCE(p.pos_short,0))) DESC
            """,
            {'ts': ts},
        )
        for r in asset_compare:
            long_ok = _within_tolerance(r['signal_long'], r['pos_long'], pct=0.005, abs_tol=2500)
            short_ok = _within_tolerance(r['signal_short'], r['pos_short'], pct=0.005, abs_tol=2500)
            if not (long_ok and short_ok):
                mismatches.append({
                    'coin': r['coin'],
                    'signal_long_usd': float(r['signal_long'] or 0),
                    'position_long_usd': float(r['pos_long'] or 0),
                    'signal_short_usd': float(r['signal_short'] or 0),
                    'position_short_usd': float(r['pos_short'] or 0),
                    'signal_wallets_long': int(r['signal_wallets_long'] or 0),
                    'position_wallets_long': int(r['pos_wallets_long'] or 0),
                    'signal_wallets_short': int(r['signal_wallets_short'] or 0),
                    'position_wallets_short': int(r['pos_wallets_short'] or 0),
                })
    _add_check(checks, 'Signal board matches raw positions by asset', len(mismatches) == 0, f'{len(mismatches)} asset mismatches found', metrics={'mismatches_preview': mismatches[:8]})

    live_result = None
    if live:
        live_wallets = wallet_list if full else wallet_list[:max_wallets]
        live_result = _live_wallet_totals(live_wallets)
        db_subset = _db_wallet_subset_totals(live_wallets, ts)
        live_result['db_completed_snapshot_for_same_wallets'] = db_subset
        live_account_ok = _within_tolerance(live_result['account_value_usd'], db_subset['account_value_usd'], pct=0.02, abs_tol=250000)
        live_open_ok = _within_tolerance(live_result['open_position_value_usd'], db_subset['open_position_value_usd'], pct=0.03, abs_tol=500000)
        _add_check(checks, 'Live Hyperliquid account value match', live_account_ok and not live_result['errors'], f"checked {live_result['wallets_ok']}/{len(live_wallets)} wallets live", metrics=_delta_metrics(live_result['account_value_usd'], db_subset['account_value_usd']))
        _add_check(checks, 'Live Hyperliquid open-position value match', live_open_ok and not live_result['errors'], f"checked {live_result['wallets_ok']}/{len(live_wallets)} wallets live", metrics=_delta_metrics(live_result['open_position_value_usd'], db_subset['open_position_value_usd']))

    error_failures = [c for c in checks if c['status'] == 'fail' and c.get('severity') == 'error']
    warning_failures = [c for c in checks if c['status'] == 'fail' and c.get('severity') != 'error']
    return {
        'generated_at_ms': now,
        'latest_signal_ts_ms': ts,
        'overall_status': 'fail' if error_failures else 'warning' if warning_failures else 'pass',
        'checks': checks,
        'totals': {
            'signal_rollup': dict(signal_rollup),
            'snapshot_rollup': dict(snapshot_rollup),
            'position_rollup': dict(position_rollup),
            'target_rollup': dict(target_rollup),
            'collector_latest': dict(collector),
            'collector_stale_seconds': stale_seconds,
        },
        'asset_mismatches': mismatches[:25],
        'live_check': live_result,
    }

@app.get('/api/signals')
def signals(limit: int = 50, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT * FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY signal DESC
        LIMIT :limit
        """,
        {'limit': limit},
    )


@app.get('/api/targets')
def targets(user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM portfolio_targets)
        SELECT * FROM portfolio_targets
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY target_weight DESC
        """
    )


@app.get('/api/flow')
def flow(limit: int = 500, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT coin, signal, confidence, wallets_long, wallets_short, wallets_flat,
               value_long_usd, value_short_usd, net_value_usd,
               value_long_pct_total, value_short_pct_total,
               net_buyer_count,
               bullish_value_flow_usd,
               bearish_value_flow_usd,
               bullish_value_flow_usd AS bullish_flow_usd,
               bearish_value_flow_usd AS bearish_flow_usd,
               net_value_flow_usd
        FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY abs(net_value_flow_usd) DESC NULLS LAST
        LIMIT :limit
        """,
        {'limit': limit},
    )

@app.get('/api/wallets')
def wallets(limit: int = 100, user: dict = Depends(require_active_subscription)):
    return fetch_all(
        """
        SELECT q.rank, q.wallet, q.score, ws.account_value_usd, ws.pnl_30d_usd,
               ws.pnl_all_time_usd, ws.max_drawdown_pct, q.qualified_at
        FROM qualified_wallets q
        LEFT JOIN LATERAL (
          SELECT * FROM wallet_scores s WHERE s.wallet=q.wallet ORDER BY s.ts_ms DESC LIMIT 1
        ) ws ON true
        WHERE q.status='active'
        ORDER BY q.rank ASC
        LIMIT :limit
        """,
        {'limit': limit},
    )


@app.get('/api/runs')
def runs(limit: int = 30, user: dict = Depends(require_active_subscription)):
    return fetch_all('SELECT * FROM collector_runs ORDER BY ts_ms DESC LIMIT :limit', {'limit': limit})


@app.get('/api/recent-orders')
def recent_orders(limit: int = 50, user: dict = Depends(require_active_subscription)):
    rows = fetch_all(
        """
        WITH completed AS (
          SELECT max(ts_ms) AS latest_ts FROM asset_signals
        ), ordered_ts AS (
          SELECT DISTINCT ts_ms FROM positions
          WHERE ts_ms <= COALESCE((SELECT latest_ts FROM completed), (SELECT max(ts_ms) FROM positions))
          ORDER BY ts_ms DESC LIMIT 2
        ), latest_ts AS (
          SELECT max(ts_ms) AS ts_ms FROM ordered_ts
        ), previous_ts AS (
          SELECT min(ts_ms) AS ts_ms FROM ordered_ts
        ), latest AS (
          SELECT p.* FROM positions p WHERE p.ts_ms=(SELECT ts_ms FROM latest_ts)
        ), previous AS (
          SELECT p.* FROM positions p WHERE p.ts_ms=(SELECT ts_ms FROM previous_ts)
        ), joined AS (
          SELECT COALESCE(l.ts_ms, (SELECT ts_ms FROM latest_ts)) AS ts_ms,
                 COALESCE(l.wallet, p.wallet) AS wallet,
                 COALESCE(l.coin, p.coin) AS coin,
                 COALESCE(l.side, p.side) AS side,
                 COALESCE(l.position_value_usd,0) - COALESCE(p.position_value_usd,0) AS delta_value_usd,
                 COALESCE(l.position_value_usd,0) AS position_value_usd,
                 COALESCE(l.size,0) - COALESCE(p.size,0) AS delta_size
          FROM latest l
          FULL OUTER JOIN previous p ON p.wallet=l.wallet AND p.coin=l.coin AND lower(p.side)=lower(l.side)
        )
        SELECT * FROM joined
        WHERE abs(delta_value_usd) > 1000
        ORDER BY abs(delta_value_usd) DESC NULLS LAST
        LIMIT :limit
        """,
        {'limit': limit},
    )
    out = []
    for r in rows:
        side_raw = str(r.get('side') or '').lower()
        delta = float(r.get('delta_value_usd') or 0)
        if side_raw.startswith('short'):
            side = 'Short' if delta >= 0 else 'Cover'
        else:
            side = 'Long' if delta >= 0 else 'Reduce'
        wallet = r.get('wallet') or ''
        out.append({
            'ts_ms': r.get('ts_ms'),
            'wallet': wallet,
            'wallet_label': f"Wallet {wallet[:4]}…{wallet[-4:]}" if wallet else 'Wallet',
            'coin': r.get('coin'),
            'side': side,
            'delta_value_usd': delta,
            'position_value_usd': float(r.get('position_value_usd') or 0),
        })
    return out

_ICON_CACHE: dict[str, tuple[float, str | None]] = {}
_ICON_TTL_SECONDS = 60 * 60 * 24 * 7
_CG_ID_OVERRIDES = {
    'BTC': 'bitcoin', 'WBTC': 'wrapped-bitcoin', 'CBTC': 'coinbase-wrapped-btc',
    'ETH': 'ethereum', 'SOL': 'solana', 'HYPE': 'hyperliquid', 'ZEC': 'zcash',
    'NEAR': 'near', 'AAVE': 'aave', 'TRX': 'tron', 'XRP': 'ripple',
    'USDC': 'usd-coin', 'USDC/CASH': 'usd-coin', 'USDT': 'tether', 'USDS': 'usds',
    'WLD': 'worldcoin-wld', 'ARB': 'arbitrum', 'AVAX': 'avalanche-2', 'BNB': 'binancecoin',
    'DOGE': 'dogecoin', 'PENGU': 'pudgy-penguins', 'ENA': 'ethena', 'ONDO': 'ondo-finance',
    'FET': 'fetch-ai', 'LTC': 'litecoin', 'LINK': 'chainlink', 'UNI': 'uniswap',
    'APT': 'aptos', 'OP': 'optimism', 'SUI': 'sui', 'DOT': 'polkadot', 'FIL': 'filecoin',
    'ATOM': 'cosmos', 'INJ': 'injective-protocol', 'JUP': 'jupiter-exchange-solana',
    'TAO': 'bittensor', 'MNT': 'mantle', 'SEI': 'sei-network', 'BLUR': 'blur',
    'ZRO': 'layerzero', 'EIGEN': 'eigenlayer', 'STRK': 'starknet', 'XLM': 'stellar',
    'XAI': 'xai', 'FARTCOIN': 'fartcoin', 'VIRTUAL': 'virtual-protocol',
    'PENDLE': 'pendle', 'KAS': 'kaspa', 'DYDX': 'dydx-chain', 'AERO': 'aerodrome-finance',
    'BONK': 'bonk', 'KBONK': 'bonk', 'GRASS': 'grass', 'KAITO': 'kaito',
    'MELANIA': 'melania-meme', 'MOODENG': 'moo-deng', 'BERA': 'berachain-bera',
}
_CG_QUERY_OVERRIDES = {
    'HYPE': 'hyperliquid', 'MELANIA': 'melania meme', 'KBONK': 'bonk', 'BONK': 'bonk',
    'WLD': 'worldcoin', 'PENGU': 'pudgy penguins', 'KAITO': 'kaito', 'GRASS': 'grass',
    'MOODENG': 'moo deng', 'FARTCOIN': 'fartcoin', 'VIRTUAL': 'virtuals protocol',
    'LAYER': 'solayer', 'USDC/CASH': 'usd coin', 'USDS': 'usds',
}

def _open_json(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Copycat/1.0 (+https://copycat.hl)',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, timeout=6) as res:
            return json.loads(res.read().decode('utf-8'))
    except Exception:
        return None

def _coingecko_icon_for_symbol(symbol: str) -> str | None:
    symbol = (symbol or '').upper().strip()
    if not symbol:
        return None
    now = time.time()
    cached = _ICON_CACHE.get(symbol)
    if cached and now - cached[0] < _ICON_TTL_SECONDS:
        return cached[1]

    image = None
    coin_id = _CG_ID_OVERRIDES.get(symbol)
    if coin_id:
        # Bulk market endpoint gives a canonical current image URL for a CoinGecko ID.
        url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=' + urllib.parse.quote(coin_id)
        payload = _open_json(url)
        if isinstance(payload, list) and payload:
            image = payload[0].get('image')

    if not image:
        query = _CG_QUERY_OVERRIDES.get(symbol, symbol)
        url = 'https://api.coingecko.com/api/v3/search?query=' + urllib.parse.quote(query)
        payload = _open_json(url)
        if isinstance(payload, dict):
            coins = payload.get('coins') or []
            def rank_key(coin: dict) -> int:
                rank = coin.get('market_cap_rank')
                return int(rank) if isinstance(rank, int) and rank > 0 else 10_000_000
            exact = [coin for coin in coins if str(coin.get('symbol') or '').upper() == symbol]
            chosen_pool = exact or coins
            chosen = sorted(chosen_pool, key=rank_key)[0] if chosen_pool else None
            if chosen:
                image = chosen.get('large') or chosen.get('small') or chosen.get('thumb')

    _ICON_CACHE[symbol] = (now, image)
    return image

@app.get('/api/token-icons')
def token_icons(symbols: str = ''):
    requested = []
    for raw in symbols.split(','):
        sym = raw.strip().upper()
        if sym and sym not in requested:
            requested.append(sym)
    requested = requested[:120]
    return {'icons': {sym: _coingecko_icon_for_symbol(sym) for sym in requested}}


@app.post('/api/billing/create-checkout-session')
def create_checkout_session(body: dict, user: dict = Depends(get_current_user)):
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail='Stripe not configured')
    interval = body.get('interval', 'monthly')
    price_id = settings.stripe_price_id_annual if interval == 'annual' else settings.stripe_price_id_monthly
    if not price_id:
        raise HTTPException(status_code=500, detail='Stripe price ID missing')
    session = stripe.checkout.Session.create(
        mode='subscription',
        payment_method_types=['card'],
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=f'{settings.public_site_url}/dashboard?checkout=success',
        cancel_url=f'{settings.public_site_url}/pricing?checkout=cancelled',
        client_reference_id=user['sub'],
        customer_email=user.get('email'),
        metadata={'supabase_user_id': user['sub']},
    )
    return {'url': session.url}


@app.post('/api/stripe/webhook')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail='Invalid Stripe webhook') from exc
    else:
        event = await request.json()

    etype = event.get('type')
    data = event.get('data', {}).get('object', {})
    if etype in ('checkout.session.completed', 'customer.subscription.updated', 'customer.subscription.deleted'):
        user_id = data.get('client_reference_id') or data.get('metadata', {}).get('supabase_user_id')
        subscription_id = data.get('subscription') or data.get('id')
        customer_id = data.get('customer')
        status = data.get('status') or 'active'
        if user_id:
            execute(
                """
                INSERT INTO subscriptions(user_id, stripe_customer_id, stripe_subscription_id, status, raw_json)
                VALUES (:user_id, :customer_id, :subscription_id, :status, CAST(:raw_json AS jsonb))
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                  status=excluded.status,
                  raw_json=excluded.raw_json,
                  updated_at=now()
                """,
                {
                    'user_id': user_id,
                    'customer_id': customer_id,
                    'subscription_id': subscription_id or f'session_{data.get("id")}',
                    'status': status,
                    'raw_json': str(data).replace("'", '"'),
                },
            )
    return {'received': True}

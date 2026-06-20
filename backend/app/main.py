from __future__ import annotations

import csv
import io
import json
import threading
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
from .copycat_data_api import (
    data_api_exposures,
    data_api_leaderboard,
    data_api_recent_events,
    data_api_status,
    data_api_wallet_fills,
    data_api_wallet_profile,
    generate_api_key,
    historical_sources,
    recent_live_orders,
    require_copycat_api_key,
)

settings = get_settings()
stripe.api_key = settings.stripe_secret_key or None

app = FastAPI(title='Hyper Wallet Tracker SaaS API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_site_url, 'http://localhost:3000'],
    allow_origin_regex=r'https://.*(onrender\.com|copycat\.hl)$',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def no_cache_api_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.get('/health')
def health():
    row = fetch_one('SELECT now() AS now')
    return {'status': 'ok', 'database': bool(row)}


@app.get('/api/me')
def me(user: dict = Depends(get_current_user)):
    return user


@app.get('/api/data/v1/status')
def copycat_data_api_status():
    return data_api_status()


@app.post('/api/data/v1/keys')
def create_copycat_data_api_key(label: str = 'Copycat API key', user: dict = Depends(require_active_subscription)):
    """Create a Copycat Data API key for the signed-in account.

    The plain key is only returned once. Store it safely.
    """
    owner = user.get('email') or user.get('sub') or None
    return generate_api_key(label=label, owner_email=owner, plan='internal')


@app.get('/api/data/v1/leaderboard')
def copycat_data_api_leaderboard(limit: int = 50, api_key: dict = Depends(require_copycat_api_key)):
    return {'status': 'ok', 'data': data_api_leaderboard(limit)}


@app.get('/api/data/v1/wallet/{wallet}')
def copycat_data_api_wallet(wallet: str, api_key: dict = Depends(require_copycat_api_key)):
    return {'status': 'ok', 'data': data_api_wallet_profile(wallet)}


@app.get('/api/data/v1/wallet/{wallet}/fills')
def copycat_data_api_fills(wallet: str, limit: int = 100, api_key: dict = Depends(require_copycat_api_key)):
    return {'status': 'ok', 'data': data_api_wallet_fills(wallet, limit)}


@app.get('/api/data/v1/exposures')
def copycat_data_api_exposure(limit: int = 100, api_key: dict = Depends(require_copycat_api_key)):
    return {'status': 'ok', 'data': data_api_exposures(limit)}


@app.get('/api/data/v1/recent-events')
def copycat_data_api_events(limit: int = 100, api_key: dict = Depends(require_copycat_api_key)):
    return {'status': 'ok', 'data': data_api_recent_events(limit)}


@app.get('/api/data/v1/historical-sources')
def copycat_data_api_historical_sources():
    return {'status': 'ok', 'data': historical_sources()}


_DASHBOARD_FEED_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_DASHBOARD_FEED_LOCK = threading.Lock()
_DASHBOARD_FEED_TTL_SECONDS = 0.85


@app.get('/api/dashboard-feed')
def dashboard_feed(user: dict = Depends(require_active_subscription)):
    """Single live dashboard payload.

    The customer dashboard polls once per second. Previously each browser tab
    made 6+ separate API/database calls every second. Two devices open at once
    could therefore create overlapping request bursts and intermittent browser
    "Failed to fetch" errors. This endpoint aggregates the whole dashboard
    and keeps a sub-second in-memory cache so multiple open devices share one
    database read cycle.
    """
    now = time.time()
    cached = _DASHBOARD_FEED_CACHE.get('data')
    if cached and now - float(_DASHBOARD_FEED_CACHE.get('ts') or 0) < _DASHBOARD_FEED_TTL_SECONDS:
        return cached

    with _DASHBOARD_FEED_LOCK:
        now = time.time()
        cached = _DASHBOARD_FEED_CACHE.get('data')
        if cached and now - float(_DASHBOARD_FEED_CACHE.get('ts') or 0) < _DASHBOARD_FEED_TTL_SECONDS:
            return cached
        try:
            insight_result = insights(user)
            feed = {
                'summary': summary(user),
                'signals': signals(limit=500, user=user),
                'targets': targets(user),
                'flow': flow(limit=500, user=user),
                'orders': recent_orders(limit=50, user=user),
                'insights': (insight_result.get('insights') if isinstance(insight_result, dict) else []) or [],
                'server_time_ms': _now_ms(),
                'cache_ttl_ms': int(_DASHBOARD_FEED_TTL_SECONDS * 1000),
            }
            _DASHBOARD_FEED_CACHE['ts'] = time.time()
            _DASHBOARD_FEED_CACHE['data'] = feed
            return feed
        except Exception:
            # If a transient database/network error happens, serve the most
            # recent good payload instead of making every open dashboard jump.
            cached = _DASHBOARD_FEED_CACHE.get('data')
            if cached:
                stale = dict(cached)
                stale['stale'] = True
                stale['warning'] = 'Serving last good dashboard payload while the live feed reconnects.'
                return stale
            raise


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
            SELECT COALESCE(sum(ws.account_value_usd),0) AS tracked_total,
                   COALESCE(max(ws.account_value_usd),0) AS largest_account_value_usd,
                   count(DISTINCT ws.wallet) AS wallets
            FROM wallet_snapshots ws
            JOIN qualified_wallets q ON q.wallet=ws.wallet AND q.status='active'
            WHERE ws.ts_ms=:ts
            """,
            {'ts': stable_ts},
        ) or {'tracked_total': 0, 'largest_account_value_usd': 0, 'wallets': 0}
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
        largest_account_value_usd = snapshot_rollup.get('largest_account_value_usd') or 0
        open_total = position_rollup['open_total'] if int(position_rollup.get('positions') or 0) > 0 else signal_rollup['signal_open_total']
        open_positions = position_rollup['positions'] if int(position_rollup.get('positions') or 0) > 0 else signal_rollup['signal_positions']
        assets = {'n': signal_rollup['assets']}
        total_value = {'total': tracked_total, 'largest_account_value_usd': largest_account_value_usd}
        open_value = {'total': open_total, 'positions': open_positions}
    else:
        total_value = fetch_one(
            """
            WITH latest AS (
              SELECT DISTINCT ON (wallet) wallet, account_value_usd
              FROM wallet_snapshots ORDER BY wallet, ts_ms DESC
            ) SELECT COALESCE(sum(account_value_usd),0) AS total,
                     COALESCE(max(account_value_usd),0) AS largest_account_value_usd
              FROM latest
            """
        ) or {'total': 0, 'largest_account_value_usd': 0}
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
    latest_run = fetch_one("SELECT ts_ms,status,message FROM collector_runs WHERE run_type='collect_once' ORDER BY ts_ms DESC LIMIT 1") or {}
    collector_age_seconds = None
    if latest_run.get('ts_ms'):
        collector_age_seconds = max(0, (_now_ms() - int(latest_run['ts_ms'])) / 1000)
    data_quality_ok = bool(stable_ts) and int(latest_wallets.get('n') or 0) >= 50 and (collector_age_seconds is None or collector_age_seconds <= 90)
    return {
        'latest_signal_ts_ms': stable_ts,
        'latest_position_ts_ms': latest_pos_ts['ts_ms'],
        'qualified_wallets': latest_wallets['n'],
        'tracked_account_value_usd': float(total_value['total'] or 0),
        'largest_account_value_usd': float(total_value.get('largest_account_value_usd') or 0),
        'tracked_open_position_value_usd': float(open_value['total'] or 0),
        'open_positions': int(open_value['positions'] or 0),
        'assets_with_signals': assets['n'],
        'data_quality_status': 'healthy' if data_quality_ok else 'checking',
        'data_quality_age_seconds': collector_age_seconds,
        'data_quality_message': '50-wallet snapshot healthy' if data_quality_ok else 'Waiting for a fresh completed collector snapshot',
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
    collector = fetch_one("SELECT * FROM collector_runs WHERE run_type='collect_once' ORDER BY ts_ms DESC LIMIT 1") or {}
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
    _add_check(checks, 'Collector freshness', stale_seconds is not None and stale_seconds <= 35, f'last completed collector run {stale_seconds:.1f}s ago' if stale_seconds is not None else 'no collector run found', 'warning')
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

    display_bad = fetch_one(
        """
        WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT count(*) AS n FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest)
          AND (value_long_usd + value_short_usd) > 0
          AND (
            ((value_long_usd >= value_short_usd) AND (value_long_usd / NULLIF(value_long_usd + value_short_usd,0)) NOT BETWEEN 0 AND 1)
            OR
            ((value_short_usd > value_long_usd) AND (value_short_usd / NULLIF(value_long_usd + value_short_usd,0)) NOT BETWEEN 0 AND 1)
          )
        """
    ) or {'n': 0}
    _add_check(checks, 'Display signal percentages are bounded', int(display_bad.get('n') or 0) == 0, f"{display_bad.get('n',0)} rows have invalid display percentages")

    flow_direction_bad = fetch_one(
        """
        WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT count(*) AS n FROM asset_signals
        WHERE ts_ms=(SELECT ts_ms FROM latest)
          AND abs(net_value_flow_usd) > 1000
          AND sign(net_value_flow_usd) <> sign(COALESCE(bullish_value_flow_usd,0) - COALESCE(bearish_value_flow_usd,0))
        """
    ) or {'n': 0}
    _add_check(checks, 'Flow read direction matches net value flow', int(flow_direction_bad.get('n') or 0) == 0, f"{flow_direction_bad.get('n',0)} rows have inconsistent flow direction")

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
    """Current Copycat Index allocation.

    This intentionally excludes USDC/CASH collateral and normalises tradable
    net exposure to 100% gross. The dashboard donut and strategy index use this
    same output so customers can see the exact allocation that powers the index.
    """
    ts, weights = _latest_index_weights()
    rows = []
    for coin, signed_weight in (weights or {}).items():
        if _index_is_margin_symbol(coin):
            continue
        signed = float(signed_weight or 0)
        rows.append({
            'ts_ms': ts,
            'coin': coin,
            'target_weight': abs(signed),
            'index_weight': signed,
            'direction': 'long' if signed >= 0 else 'short',
            'signal': signed,
            'confidence': 'Index',
            'method': _INDEX_METHOD_VERSION,
            'note': 'USDC margin excluded; weights are normalised tradable exposure.',
        })
    rows.sort(key=lambda r: r['target_weight'], reverse=True)
    return rows

@app.get('/api/insights')
def insights(user: dict = Depends(require_active_subscription)):
    # At-a-glance trader/analyst insights from the latest completed snapshot.
    # Customer-facing signal strength is the signed value-weighted directional
    # majority so it aligns with the long-vs-short exposure bars.
    ts_row = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    ts = ts_row.get('ts_ms')
    if not ts:
        return {'status': 'empty', 'insights': []}
    rows = fetch_all("""
        SELECT coin, signal, confidence, wallets_long, wallets_short,
               value_long_usd, value_short_usd, net_value_usd,
               net_buyer_count, bullish_value_flow_usd, bearish_value_flow_usd,
               net_value_flow_usd, total_tracked_value_usd
        FROM asset_signals
        WHERE ts_ms=:ts
    """, {'ts': ts})
    if not rows:
        return {'status': 'empty', 'insights': []}

    def display_signal(r: dict[str, Any]) -> float:
        long_v = _safe_float(r.get('value_long_usd'))
        short_v = _safe_float(r.get('value_short_usd'))
        total = long_v + short_v
        if total <= 0:
            return _safe_float(r.get('signal'))
        return long_v / total if long_v >= short_v else -(short_v / total)

    top_signal = max(rows, key=lambda r: abs(display_signal(r)))
    accumulation = max(rows, key=lambda r: _safe_float(r.get('net_value_flow_usd')))
    distribution = min(rows, key=lambda r: _safe_float(r.get('net_value_flow_usd')))
    most_traded = max(rows, key=lambda r: _safe_float(r.get('bullish_value_flow_usd')) + _safe_float(r.get('bearish_value_flow_usd')))

    def disagreement_score(r: dict[str, Any]) -> float:
        long_w = _safe_float(r.get('wallets_long'))
        short_w = _safe_float(r.get('wallets_short'))
        wallet_bias = (long_w - short_w) / max(1.0, long_w + short_w)
        value_bias = _safe_float(r.get('net_value_usd')) / max(1.0, _safe_float(r.get('value_long_usd')) + _safe_float(r.get('value_short_usd')))
        return abs(wallet_bias - value_bias)

    disagreement = max(rows, key=disagreement_score)
    return {
        'status': 'ok',
        'ts_ms': ts,
        'insights': [
            {'type': 'top_signal', 'label': 'Top conviction asset', 'coin': top_signal.get('coin'), 'detail': f"Signal {display_signal(top_signal):.4f} · {top_signal.get('confidence')}", 'row': top_signal},
            {'type': 'accumulation', 'label': 'Biggest accumulation', 'coin': accumulation.get('coin'), 'detail': f"Net flow ${float(accumulation.get('net_value_flow_usd') or 0):,.0f}", 'row': accumulation},
            {'type': 'distribution', 'label': 'Biggest distribution', 'coin': distribution.get('coin'), 'detail': f"Net flow ${float(distribution.get('net_value_flow_usd') or 0):,.0f}", 'row': distribution},
            {'type': 'most_traded', 'label': 'Most traded asset', 'coin': most_traded.get('coin'), 'detail': f"Gross flow ${float((_safe_float(most_traded.get('bullish_value_flow_usd')) + _safe_float(most_traded.get('bearish_value_flow_usd')))):,.0f}", 'row': most_traded},
            {'type': 'disagreement', 'label': 'Wallet count vs value disagreement', 'coin': disagreement.get('coin'), 'detail': f"{disagreement.get('wallets_long')} long / {disagreement.get('wallets_short')} short · net ${float(disagreement.get('net_value_usd') or 0):,.0f}", 'row': disagreement},
        ]
    }


@app.get('/api/ranking-audit')
def ranking_audit(limit: int = 50, user: dict = Depends(require_active_subscription)):
    rows = fetch_all("""
        SELECT q.rank, q.wallet, q.score AS active_score, q.qualified_at_ms,
               s.ts_ms, s.score, s.qualifies, s.account_value_usd, s.pnl_30d_usd,
               s.pnl_all_time_usd, s.max_drawdown_pct, s.consistency_score,
               s.anti_fluke_score, s.metrics_json
        FROM qualified_wallets q
        LEFT JOIN LATERAL (
          SELECT * FROM wallet_scores ws WHERE ws.wallet=q.wallet ORDER BY ws.ts_ms DESC LIMIT 1
        ) s ON true
        WHERE q.status='active'
        ORDER BY q.rank ASC
        LIMIT :limit
    """, {'limit': limit})
    out = []
    for r in rows:
        metrics = r.get('metrics_json') or {}
        if isinstance(metrics, str):
            try: metrics = json.loads(metrics)
            except Exception: metrics = {}
        out.append({
            **{k: v for k, v in dict(r).items() if k != 'metrics_json'},
            'score_components': metrics.get('score_components') or {},
            'ranking_formula': metrics.get('ranking_formula') or 'unknown',
            'disqualifiers': metrics.get('disqualifiers') or [],
            'position_count': metrics.get('position_count'),
            'largest_position_share': metrics.get('largest_position_share'),
            'real_pnl_windows': metrics.get('real_pnl_windows'),
            'active_days_observed': metrics.get('active_days_observed'),
        })
    return {'status': 'ok', 'method': 'v2_profit_quality', 'wallets': out}


@app.get('/api/signal-explain')
def signal_explain(coin: str, limit: int = 15, user: dict = Depends(require_active_subscription)):
    coin = coin.upper().strip()
    latest_signal = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    ts = latest_signal.get('ts_ms')
    if not ts:
        return {'status': 'empty', 'coin': coin, 'contributors': []}
    rows = fetch_all("""
        SELECT p.wallet, p.coin, p.side, p.position_value_usd, p.size, p.unrealized_pnl_usd,
               COALESCE(ws.account_value_usd,0) AS account_value_usd,
               COALESCE(score.score,50) AS wallet_score
        FROM positions p
        JOIN qualified_wallets q ON q.wallet=p.wallet AND q.status='active'
        LEFT JOIN wallet_snapshots ws ON ws.wallet=p.wallet AND ws.ts_ms=p.ts_ms
        LEFT JOIN LATERAL (
          SELECT s.score FROM wallet_scores s WHERE s.wallet=p.wallet ORDER BY s.ts_ms DESC LIMIT 1
        ) score ON true
        WHERE p.ts_ms=:ts AND upper(p.coin)=:coin
        ORDER BY p.position_value_usd DESC
        LIMIT :limit
    """, {'ts': ts, 'coin': coin, 'limit': limit})
    total_value = sum(_safe_float(r.get('position_value_usd')) for r in rows)
    contributors = []
    for r in rows:
        wallet = r.get('wallet') or ''
        value = _safe_float(r.get('position_value_usd'))
        contributors.append({
            'wallet': wallet,
            'wallet_label': f"Wallet {wallet[:4]}…{wallet[-4:]}" if wallet else 'Wallet',
            'side': r.get('side'),
            'position_value_usd': value,
            'share_of_coin_value': value / max(total_value, 1),
            'account_value_usd': _safe_float(r.get('account_value_usd')),
            'wallet_score': _safe_float(r.get('wallet_score')),
            'unrealized_pnl_usd': _safe_float(r.get('unrealized_pnl_usd')),
        })
    concentration = max([c['share_of_coin_value'] for c in contributors] or [0])
    return {'status': 'ok', 'coin': coin, 'ts_ms': ts, 'total_explained_value_usd': total_value, 'top_wallet_concentration': concentration, 'contributors': contributors}


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
    # Prefer stored Hyperliquid WebSocket events when the live-events worker is running.
    # This lets the dashboard show tracked-wallet fills much faster than waiting for
    # a full 50-wallet position-diff collector cycle.
    live_rows = recent_live_orders(limit)
    if live_rows:
        return live_rows[:limit]

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
                 COALESCE(p.position_value_usd,0) AS previous_value_usd,
                 COALESCE(l.size,0) - COALESCE(p.size,0) AS delta_size
          FROM latest l
          FULL OUTER JOIN previous p ON p.wallet=l.wallet AND p.coin=l.coin AND lower(p.side)=lower(l.side)
        )
        SELECT * FROM joined
        WHERE abs(delta_value_usd) > 1000
        ORDER BY ts_ms DESC, abs(delta_value_usd) DESC NULLS LAST
        LIMIT :limit
        """,
        {'limit': limit},
    )
    out = []
    for r in rows:
        side_raw = str(r.get('side') or '').lower()
        delta = float(r.get('delta_value_usd') or 0)
        current_value = float(r.get('position_value_usd') or 0)
        previous_value = float(r.get('previous_value_usd') or 0)
        opened = previous_value <= 100 and current_value > 100
        closed = current_value <= 100 and previous_value > 100
        if side_raw.startswith('short'):
            if opened:
                action = 'Open short'
            elif closed:
                action = 'Close short'
            elif delta > 0:
                action = 'Add short'
            else:
                action = 'Reduce short'
        elif side_raw.startswith('long'):
            if opened:
                action = 'Open long'
            elif closed:
                action = 'Close long'
            elif delta > 0:
                action = 'Add long'
            else:
                action = 'Reduce long'
        else:
            action = 'Buy' if delta > 0 else 'Reduce'
        wallet = r.get('wallet') or ''
        out.append({
            'ts_ms': r.get('ts_ms'),
            'wallet': wallet,
            'wallet_label': f"Wallet {wallet[:4]}…{wallet[-4:]}" if wallet else 'Wallet',
            'coin': 'USDC' if str(r.get('coin') or '').upper() in ('USDC/CASH', 'CASH') else r.get('coin'),
            'side': action,
            'delta_value_usd': delta,
            'position_value_usd': current_value,
            'previous_value_usd': previous_value,
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



# -------------------------
# Copycat Live Strategy Index
# -------------------------
_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_INDEX_CACHE_TTL_SECONDS = 2.0
_INDEX_WRITE_INTERVAL_MS = 60_000
_INDEX_METHOD_VERSION = 'copycat_live_index_v2_no_margin_signed_exposure'
_FEE_SLIPPAGE_RATE = 0.0015  # 15 bps round-trip buffer on rebalance turnover.
_SPX_CACHE: dict[str, Any] = {'ts': 0.0, 'price': None}
_SPX_CACHE_TTL_SECONDS = 60 * 30


def _normalise_index_symbol(symbol: str) -> str:
    s = str(symbol or '').upper().strip()
    if s in ('USDC/CASH', 'USDCCASH', 'USDCASH', 'CASH', 'USD'):
        return 'USDC'
    return ''.join(ch for ch in s if ch.isalnum())


def _ensure_index_table() -> None:
    execute("""
        CREATE TABLE IF NOT EXISTS strategy_index_points (
          id bigserial PRIMARY KEY,
          ts_ms bigint NOT NULL UNIQUE,
          ts timestamptz NOT NULL DEFAULT now(),
          copycat_nav double precision NOT NULL,
          btc_nav double precision NOT NULL,
          eth_nav double precision NOT NULL,
          spx_nav double precision NOT NULL DEFAULT 100,
          copycat_return_pct double precision NOT NULL,
          btc_return_pct double precision NOT NULL,
          eth_return_pct double precision NOT NULL,
          spx_return_pct double precision NOT NULL DEFAULT 0,
          method text NOT NULL,
          weights_json jsonb NOT NULL,
          prices_json jsonb NOT NULL,
          benchmark_prices_json jsonb NOT NULL,
          metadata_json jsonb NOT NULL
        )
    """)
    execute("ALTER TABLE strategy_index_points ADD COLUMN IF NOT EXISTS spx_nav double precision NOT NULL DEFAULT 100")
    execute("ALTER TABLE strategy_index_points ADD COLUMN IF NOT EXISTS spx_return_pct double precision NOT NULL DEFAULT 0")
    execute("CREATE INDEX IF NOT EXISTS idx_strategy_index_points_ts ON strategy_index_points(ts_ms DESC)")


def _ensure_backtest_table() -> None:
    execute("""
        CREATE TABLE IF NOT EXISTS strategy_backtest_points (
          id bigserial PRIMARY KEY,
          ts_ms bigint NOT NULL UNIQUE,
          ts timestamptz NOT NULL DEFAULT now(),
          copycat_nav double precision NOT NULL,
          btc_nav double precision NOT NULL,
          eth_nav double precision NOT NULL,
          spx_nav double precision NOT NULL,
          copycat_return_pct double precision NOT NULL,
          btc_return_pct double precision NOT NULL,
          eth_return_pct double precision NOT NULL,
          spx_return_pct double precision NOT NULL,
          method text NOT NULL DEFAULT 'copycat_backtest_v1_weekly',
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    execute("CREATE INDEX IF NOT EXISTS idx_strategy_backtest_points_ts ON strategy_backtest_points(ts_ms DESC)")


def _hl_all_mids() -> dict[str, float]:
    payload = _hl_info({'type': 'allMids'})
    if not isinstance(payload, dict):
        return {}
    out: dict[str, float] = {'USDC': 1.0}
    for k, v in payload.items():
        sym = _normalise_index_symbol(k)
        px = _safe_float(v)
        if sym and px > 0:
            out[sym] = px
    return out


def _spx_latest_price() -> float | None:
    """Return latest S&P 500 close without blocking the index if unavailable.

    Stooq's CSV endpoint is used because it needs no API key. If the external
    quote cannot be reached, the live index keeps the last SPX value rather than
    failing the whole Copycat chart.
    """
    now = time.time()
    cached = _SPX_CACHE.get('price')
    if cached and now - float(_SPX_CACHE.get('ts') or 0) < _SPX_CACHE_TTL_SECONDS:
        return float(cached)
    try:
        url = 'https://stooq.com/q/l/?s=%5Espx&i=d'
        with urllib.request.urlopen(url, timeout=8) as resp:
            text_body = resp.read().decode('utf-8', errors='replace')
        rows = list(csv.DictReader(io.StringIO(text_body)))
        if not rows:
            return float(cached) if cached else None
        px = _safe_float(rows[0].get('Close'))
        if px > 0:
            _SPX_CACHE['ts'] = now
            _SPX_CACHE['price'] = px
            return px
    except Exception:
        return float(cached) if cached else None
    return float(cached) if cached else None


def _index_is_margin_symbol(symbol: str) -> bool:
    # USDC/USDT-style balances are margin/collateral on Hyperliquid. They are
    # deliberately excluded from the Copycat Strategy Index so the index reflects
    # tradable exposure, not unused margin.
    return _normalise_index_symbol(symbol) in {
        'USDC', 'USDT', 'USDE', 'USDS', 'USDL', 'USD', 'DAI', 'FDUSD', 'TUSD', 'CASH'
    }


def _latest_index_weights() -> tuple[int | None, dict[str, float]]:
    """Return signed 1x-gross Copycat Index weights from the latest signal snapshot.

    The dashboard can show USDC as collateral/margin, but the performance index
    must not treat that collateral as a portfolio holding. This method uses the
    qualified-wallet net exposure by asset:

        signed exposure = value_long_usd - value_short_usd
        index weight    = signed exposure / sum(abs(signed exposure))

    That gives a 100% gross exposure model where positive weights are longs and
    negative weights are shorts. It is the allocation a user would need to follow
    if they wanted to mirror the Copycat Index methodology.
    """
    latest = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    ts = latest.get('ts_ms')
    if not ts:
        return None, {}

    rows = fetch_all(
        """
        SELECT coin, value_long_usd, value_short_usd, net_value_usd
        FROM asset_signals
        WHERE ts_ms=:ts
          AND (COALESCE(value_long_usd,0) + COALESCE(value_short_usd,0)) > 0
        """,
        {'ts': ts},
    )
    raw: dict[str, float] = {}
    for r in rows:
        sym = _normalise_index_symbol(r.get('coin'))
        if not sym or _index_is_margin_symbol(sym):
            continue
        net = _safe_float(r.get('net_value_usd'))
        if net == 0:
            net = _safe_float(r.get('value_long_usd')) - _safe_float(r.get('value_short_usd'))
        if abs(net) <= 0:
            continue
        raw[sym] = raw.get(sym, 0.0) + net

    denom = sum(abs(v) for v in raw.values())
    if denom > 0:
        return ts, {k: v / denom for k, v in raw.items() if abs(v) > 0}

    fallback_ts = fetch_one('SELECT max(ts_ms) AS ts_ms FROM portfolio_targets') or {'ts_ms': None}
    fts = fallback_ts.get('ts_ms')
    if not fts:
        return ts, {}
    target_rows = fetch_all('SELECT coin,target_weight,signal FROM portfolio_targets WHERE ts_ms=:ts', {'ts': fts})
    raw = {}
    for r in target_rows:
        sym = _normalise_index_symbol(r.get('coin'))
        if not sym or _index_is_margin_symbol(sym):
            continue
        w = abs(_safe_float(r.get('target_weight')))
        if w <= 0:
            continue
        sign = -1.0 if _safe_float(r.get('signal')) < 0 else 1.0
        raw[sym] = raw.get(sym, 0.0) + sign * w
    denom = sum(abs(v) for v in raw.values())
    return fts, ({k: v / denom for k, v in raw.items()} if denom > 0 else {})


def _prices_for_symbols(mids: dict[str, float], symbols: list[str] | set[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for raw in symbols:
        sym = _normalise_index_symbol(raw)
        if sym == 'USDC':
            out[sym] = 1.0
            continue
        px = mids.get(sym)
        if px and px > 0:
            out[sym] = float(px)
    return out


def _portfolio_return(prev_weights: dict[str, float], prev_prices: dict[str, float], current_prices: dict[str, float]) -> tuple[float, list[str]]:
    ret = 0.0
    missing: list[str] = []
    for sym, w in prev_weights.items():
        p0 = _safe_float(prev_prices.get(sym))
        p1 = _safe_float(current_prices.get(sym))
        if sym == 'USDC':
            continue
        if p0 <= 0 or p1 <= 0:
            missing.append(sym)
            continue
        ret += w * ((p1 / p0) - 1.0)
    return ret, missing


def _turnover(prev_weights: dict[str, float], next_weights: dict[str, float]) -> float:
    keys = set(prev_weights) | set(next_weights)
    return 0.5 * sum(abs(_safe_float(next_weights.get(k)) - _safe_float(prev_weights.get(k))) for k in keys)


def _insert_index_point(ts_ms: int, copycat_nav: float, btc_nav: float, eth_nav: float, spx_nav: float, weights: dict[str, float], prices: dict[str, float], benchmark_prices: dict[str, float], metadata: dict[str, Any]) -> None:
    execute("""
        INSERT INTO strategy_index_points(ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav, copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct, method, weights_json, prices_json, benchmark_prices_json, metadata_json)
        VALUES (:ts_ms, :copycat_nav, :btc_nav, :eth_nav, :spx_nav, :copycat_return_pct, :btc_return_pct, :eth_return_pct, :spx_return_pct, :method, CAST(:weights AS jsonb), CAST(:prices AS jsonb), CAST(:benchmarks AS jsonb), CAST(:metadata AS jsonb))
        ON CONFLICT (ts_ms) DO NOTHING
    """, {
        'ts_ms': ts_ms,
        'copycat_nav': copycat_nav,
        'btc_nav': btc_nav,
        'eth_nav': eth_nav,
        'spx_nav': spx_nav,
        'copycat_return_pct': copycat_nav - 100.0,
        'btc_return_pct': btc_nav - 100.0,
        'eth_return_pct': eth_nav - 100.0,
        'spx_return_pct': spx_nav - 100.0,
        'method': _INDEX_METHOD_VERSION,
        'weights': json.dumps(weights),
        'prices': json.dumps(prices),
        'benchmarks': json.dumps(benchmark_prices),
        'metadata': json.dumps(metadata),
    })


def _load_index_points(limit: int = 500) -> list[dict[str, Any]]:
    rows = fetch_all("""
        SELECT ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav, copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct, method, weights_json, prices_json, benchmark_prices_json, metadata_json
        FROM strategy_index_points
        WHERE method=:method
        ORDER BY ts_ms DESC
        LIMIT :limit
    """, {'limit': limit, 'method': _INDEX_METHOD_VERSION})
    rows = list(reversed(rows))
    for r in rows:
        for key in ('weights_json', 'prices_json', 'benchmark_prices_json', 'metadata_json'):
            val = r.get(key)
            if isinstance(val, str):
                try:
                    r[key] = json.loads(val)
                except Exception:
                    r[key] = {}
    return rows


def _update_strategy_index_locked(force: bool = False) -> dict[str, Any]:
    _ensure_index_table()
    now_ms = _now_ms()
    target_ts, weights = _latest_index_weights()
    needed_symbols = set(weights) | {'BTC', 'ETH'}
    mids = _hl_all_mids()
    current_prices = _prices_for_symbols(mids, needed_symbols)
    spx_price = _spx_latest_price()
    benchmark_prices = {'BTC': current_prices.get('BTC'), 'ETH': current_prices.get('ETH'), 'SPX': spx_price}

    rows = _load_index_points(limit=500)
    if not rows:
        # Baseline starts at 100.00 using the first live target/price snapshot.
        seed_prices = _prices_for_symbols(mids, set(weights))
        _insert_index_point(
            now_ms,
            100.0,
            100.0,
            100.0,
            100.0,
            weights,
            seed_prices,
            {'BTC': benchmark_prices.get('BTC') or 0, 'ETH': benchmark_prices.get('ETH') or 0, 'SPX': benchmark_prices.get('SPX') or 0},
            {
                'target_ts_ms': target_ts,
                'event': 'baseline',
                'fee_slippage_rate': _FEE_SLIPPAGE_RATE,
                'note': 'Copycat Live Index baseline. No historical backfill or hindsight.',
            },
        )
        rows = _load_index_points(limit=500)

    last = rows[-1]
    last_ts = int(last.get('ts_ms') or 0)
    if force or now_ms - last_ts >= _INDEX_WRITE_INTERVAL_MS:
        prev_weights = last.get('weights_json') or {'USDC': 1.0}
        prev_prices = last.get('prices_json') or {}
        prev_benchmarks = last.get('benchmark_prices_json') or {}
        current_target_prices = _prices_for_symbols(mids, set(prev_weights) | set(weights))
        raw_return, missing = _portfolio_return(prev_weights, prev_prices, current_target_prices)
        turn = _turnover(prev_weights, weights)
        net_return = raw_return - (turn * _FEE_SLIPPAGE_RATE)
        copycat_nav = max(0.0, _safe_float(last.get('copycat_nav')) * (1.0 + net_return))
        btc_px0 = _safe_float(prev_benchmarks.get('BTC'))
        eth_px0 = _safe_float(prev_benchmarks.get('ETH'))
        spx_px0 = _safe_float(prev_benchmarks.get('SPX'))
        btc_px1 = _safe_float(benchmark_prices.get('BTC'))
        eth_px1 = _safe_float(benchmark_prices.get('ETH'))
        spx_px1 = _safe_float(benchmark_prices.get('SPX'))
        btc_nav = _safe_float(last.get('btc_nav')) * ((btc_px1 / btc_px0) if btc_px0 > 0 and btc_px1 > 0 else 1.0)
        eth_nav = _safe_float(last.get('eth_nav')) * ((eth_px1 / eth_px0) if eth_px0 > 0 and eth_px1 > 0 else 1.0)
        spx_nav = _safe_float(last.get('spx_nav')) * ((spx_px1 / spx_px0) if spx_px0 > 0 and spx_px1 > 0 else 1.0)
        next_prices = _prices_for_symbols(mids, set(weights))
        _insert_index_point(
            now_ms,
            copycat_nav,
            btc_nav,
            eth_nav,
            spx_nav,
            weights,
            next_prices,
            {'BTC': btc_px1 or btc_px0 or 0, 'ETH': eth_px1 or eth_px0 or 0, 'SPX': spx_px1 or spx_px0 or 0},
            {
                'target_ts_ms': target_ts,
                'event': 'mark_and_rebalance',
                'raw_return': raw_return,
                'turnover': turn,
                'fee_slippage_cost': turn * _FEE_SLIPPAGE_RATE,
                'missing_prices': missing,
                'fee_slippage_rate': _FEE_SLIPPAGE_RATE,
            },
        )
        rows = _load_index_points(limit=500)
        last = rows[-1]

    # Add a non-persisted live mark so the chart is current between stored points.
    prev_weights = last.get('weights_json') or {'USDC': 1.0}
    prev_prices = last.get('prices_json') or {}
    prev_benchmarks = last.get('benchmark_prices_json') or {}
    live_prices = _prices_for_symbols(mids, set(prev_weights))
    live_return, missing_live = _portfolio_return(prev_weights, prev_prices, live_prices)
    live_copycat_nav = max(0.0, _safe_float(last.get('copycat_nav')) * (1.0 + live_return))
    btc_px0 = _safe_float(prev_benchmarks.get('BTC'))
    eth_px0 = _safe_float(prev_benchmarks.get('ETH'))
    spx_px0 = _safe_float(prev_benchmarks.get('SPX'))
    btc_px1 = _safe_float(benchmark_prices.get('BTC'))
    eth_px1 = _safe_float(benchmark_prices.get('ETH'))
    spx_px1 = _safe_float(benchmark_prices.get('SPX'))
    live_btc_nav = _safe_float(last.get('btc_nav')) * ((btc_px1 / btc_px0) if btc_px0 > 0 and btc_px1 > 0 else 1.0)
    live_eth_nav = _safe_float(last.get('eth_nav')) * ((eth_px1 / eth_px0) if eth_px0 > 0 and eth_px1 > 0 else 1.0)
    live_spx_nav = _safe_float(last.get('spx_nav')) * ((spx_px1 / spx_px0) if spx_px0 > 0 and spx_px1 > 0 else 1.0)
    live_point = {
        'ts_ms': now_ms,
        'copycat_nav': live_copycat_nav,
        'btc_nav': live_btc_nav,
        'eth_nav': live_eth_nav,
        'spx_nav': live_spx_nav,
        'copycat_return_pct': live_copycat_nav - 100.0,
        'btc_return_pct': live_btc_nav - 100.0,
        'eth_return_pct': live_eth_nav - 100.0,
        'spx_return_pct': live_spx_nav - 100.0,
        'live': True,
    }
    points = rows + ([live_point] if now_ms > int(rows[-1].get('ts_ms') or 0) else [])
    start = points[0] if points else live_point
    latest = points[-1] if points else live_point
    daily_returns = []
    for i in range(1, len(points)):
        prev = _safe_float(points[i - 1].get('copycat_nav'))
        cur = _safe_float(points[i].get('copycat_nav'))
        if prev > 0:
            daily_returns.append((cur / prev) - 1.0)
    peak = -1.0
    max_drawdown = 0.0
    for p in points:
        nav = _safe_float(p.get('copycat_nav'))
        peak = max(peak, nav)
        if peak > 0:
            max_drawdown = min(max_drawdown, (nav / peak) - 1.0)
    weights_sorted = sorted((weights or {}).items(), key=lambda kv: abs(kv[1]), reverse=True)[:10]
    return {
        'status': 'ok',
        'method': _INDEX_METHOD_VERSION,
        'start_ts_ms': start.get('ts_ms'),
        'latest_ts_ms': latest.get('ts_ms'),
        'copycat_nav': latest.get('copycat_nav'),
        'btc_nav': latest.get('btc_nav'),
        'eth_nav': latest.get('eth_nav'),
        'spx_nav': latest.get('spx_nav'),
        'copycat_return_pct': latest.get('copycat_return_pct'),
        'btc_return_pct': latest.get('btc_return_pct'),
        'eth_return_pct': latest.get('eth_return_pct'),
        'spx_return_pct': latest.get('spx_return_pct'),
        'max_drawdown_pct': max_drawdown * 100.0,
        'points_count': len(points),
        'current_weights': [{'coin': k, 'weight': abs(v), 'signed_weight': v, 'direction': 'long' if v >= 0 else 'short'} for k, v in weights_sorted],
        'points': [
            {
                'ts_ms': p.get('ts_ms'),
                'copycat_nav': p.get('copycat_nav'),
                'btc_nav': p.get('btc_nav'),
                'eth_nav': p.get('eth_nav'),
                'spx_nav': p.get('spx_nav'),
                'copycat_return_pct': p.get('copycat_return_pct'),
                'btc_return_pct': p.get('btc_return_pct'),
                'eth_return_pct': p.get('eth_return_pct'),
                'spx_return_pct': p.get('spx_return_pct'),
                'live': bool(p.get('live')),
            } for p in points
        ],
        'metadata': {
            'benchmark_assets': ['BTC', 'ETH', 'S&P 500'],
            'allocation_basis': 'signed net exposure, excluding USDC margin collateral',
            'fee_slippage_rate': _FEE_SLIPPAGE_RATE,
            'write_interval_ms': _INDEX_WRITE_INTERVAL_MS,
            'target_ts_ms': target_ts,
            'missing_live_prices': missing_live,
            'note': 'Live model index only. Uses signed net exposure weights excluding USDC margin collateral; no historical backfill or hindsight.',
            'spx_price_available': bool(spx_price),
        },
    }


def _load_backtest_points(limit: int = 500) -> list[dict[str, Any]]:
    _ensure_backtest_table()
    rows = fetch_all("""
        SELECT ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav, copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct, method, metadata_json
        FROM strategy_backtest_points
        ORDER BY ts_ms ASC
        LIMIT :limit
    """, {'limit': limit})
    for r in rows:
        val = r.get('metadata_json')
        if isinstance(val, str):
            try:
                r['metadata_json'] = json.loads(val)
            except Exception:
                r['metadata_json'] = {}
    return rows


@app.get('/api/performance-backtest')
@app.get('/api/backtest-index')
def performance_backtest():
    """Return real backtest points for the public homepage chart.

    This endpoint deliberately does not fabricate 1Y performance. A separate
    backtest loader should write validated weekly Copycat methodology rows into
    strategy_backtest_points. Until then, the frontend will show the live index
    with a clear pending/backtest warning instead of misleading customers.
    """
    rows = _load_backtest_points(limit=500)
    if not rows:
        return {
            'status': 'pending',
            'mode': 'backtest',
            'points': [],
            'warning': 'Copycat 1Y backtest is not populated yet. Showing live index until validated backtest rows are loaded.',
            'metadata': {
                'benchmark_assets': ['BTC', 'ETH', 'S&P 500'],
                'allocation_basis': 'weekly simulated Copycat methodology; signed net exposure excluding USDC margin collateral',
                'note': 'Backtest endpoint only returns persisted validated rows; it does not generate fake historical performance.',
            },
        }
    latest = rows[-1]
    start = rows[0]
    points = [
        {
            'ts_ms': r.get('ts_ms'),
            'copycat_nav': r.get('copycat_nav'),
            'btc_nav': r.get('btc_nav'),
            'eth_nav': r.get('eth_nav'),
            'spx_nav': r.get('spx_nav'),
            'copycat_return_pct': r.get('copycat_return_pct'),
            'btc_return_pct': r.get('btc_return_pct'),
            'eth_return_pct': r.get('eth_return_pct'),
            'spx_return_pct': r.get('spx_return_pct'),
            'live': False,
        } for r in rows
    ]
    peak = -1.0
    max_drawdown = 0.0
    for p in points:
        nav_value = _safe_float(p.get('copycat_nav'))
        peak = max(peak, nav_value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (nav_value / peak) - 1.0)
    return {
        'status': 'ok',
        'mode': 'backtest',
        'method': latest.get('method') or 'copycat_backtest_v1_weekly',
        'start_ts_ms': start.get('ts_ms'),
        'latest_ts_ms': latest.get('ts_ms'),
        'copycat_nav': latest.get('copycat_nav'),
        'btc_nav': latest.get('btc_nav'),
        'eth_nav': latest.get('eth_nav'),
        'spx_nav': latest.get('spx_nav'),
        'copycat_return_pct': latest.get('copycat_return_pct'),
        'btc_return_pct': latest.get('btc_return_pct'),
        'eth_return_pct': latest.get('eth_return_pct'),
        'spx_return_pct': latest.get('spx_return_pct'),
        'max_drawdown_pct': max_drawdown * 100.0,
        'points_count': len(points),
        'points': points,
        'metadata': {
            'benchmark_assets': ['BTC', 'ETH', 'S&P 500'],
            'allocation_basis': 'weekly simulated Copycat methodology; signed net exposure excluding USDC margin collateral',
            'note': 'Simulated historical backtest. Not live performance and not a guarantee of future results.',
        },
    }


@app.get('/api/performance-index')
def performance_index(force: bool = False):
    now = time.time()
    if not force and _INDEX_CACHE.get('data') and now - float(_INDEX_CACHE.get('ts') or 0) < _INDEX_CACHE_TTL_SECONDS:
        return _INDEX_CACHE['data']
    with _INDEX_LOCK:
        now = time.time()
        if not force and _INDEX_CACHE.get('data') and now - float(_INDEX_CACHE.get('ts') or 0) < _INDEX_CACHE_TTL_SECONDS:
            return _INDEX_CACHE['data']
        try:
            data = _update_strategy_index_locked(force=force)
        except Exception as exc:
            cached = _INDEX_CACHE.get('data')
            if cached:
                stale = dict(cached)
                stale['stale'] = True
                stale['warning'] = f'Performance index using last good value while live price feed reconnects: {str(exc)[:180]}'
                return stale
            raise HTTPException(status_code=503, detail=f'Performance index is not ready: {str(exc)[:220]}') from exc
        _INDEX_CACHE['ts'] = time.time()
        _INDEX_CACHE['data'] = data
        return data


@app.get('/api/performance-index/audit')
def performance_index_audit():
    try:
        data = performance_index(force=True)
        checks = []
        points = data.get('points') or []
        checks.append({'name': 'Index has baseline point', 'status': 'pass' if len(points) >= 1 else 'fail', 'detail': f'{len(points)} points'})
        checks.append({'name': 'BTC benchmark present', 'status': 'pass' if data.get('btc_nav') else 'fail', 'detail': f"BTC NAV {data.get('btc_nav')}"})
        checks.append({'name': 'ETH benchmark present', 'status': 'pass' if data.get('eth_nav') else 'fail', 'detail': f"ETH NAV {data.get('eth_nav')}"})
        checks.append({'name': 'S&P 500 benchmark present', 'status': 'pass' if data.get('spx_nav') else 'warning', 'detail': f"S&P 500 NAV {data.get('spx_nav')}"})
        weights = data.get('current_weights') or []
        checks.append({'name': 'Current Copycat weights available', 'status': 'pass' if weights else 'fail', 'detail': f'{len(weights)} top weights returned'})
        stable_weights = [w for w in weights if str(w.get('coin','')).upper() in ('USDC','USDC/CASH','CASH','USD','USDT')]
        checks.append({'name': 'USDC margin excluded from index', 'status': 'pass' if not stable_weights else 'fail', 'detail': 'no collateral assets in index weights' if not stable_weights else f"unexpected collateral weights: {stable_weights[:3]}"})
        weight_sum = sum(float(w.get('weight') or 0) for w in weights)
        checks.append({'name': 'Index weights sum to 100% gross exposure', 'status': 'pass' if 0.995 <= weight_sum <= 1.005 else 'fail', 'detail': f'gross weight sum={weight_sum:.6f}'})
        missing = (data.get('metadata') or {}).get('missing_live_prices') or []
        checks.append({'name': 'Live prices available for current weights', 'status': 'pass' if not missing else 'warning', 'detail': f"missing: {', '.join(missing[:8])}" if missing else 'all live prices available'})
        overall = 'pass' if all(c['status'] == 'pass' for c in checks) else 'warning' if any(c['status'] == 'warning' for c in checks) else 'fail'
        return {'status': overall, 'checks': checks, 'index': data}
    except Exception as exc:
        return {'status': 'fail', 'checks': [{'name': 'Performance index audit', 'status': 'fail', 'detail': str(exc)[:300]}]}

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

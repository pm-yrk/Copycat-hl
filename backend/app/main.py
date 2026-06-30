from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

import stripe
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from .auth import get_current_user, require_active_subscription
from .db import fetch_all, fetch_one, execute, engine
from .settings import get_settings
from .owned_data import owned_universe_stats
from .copycat_data_api import (
    data_api_exposures,
    ensure_copycat_data_api,
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
from .copycat_data_lake import (
    backfill_coverage,
    historical_fills,
    leaderboard_preview,
    leaderboard_v2,
    quality_snapshot,
    token_screener,
    token_screener_preview,
    wallet_universe,
)


from .platform_v1 import (
    asset_detail as platform_asset_detail,
    asset_details as platform_asset_details,
    coverage_preview as platform_coverage_preview,
    ensure_platform_tables_once,
    platform_health as platform_health_payload,
    public_leaderboard_preview as platform_leaderboard_preview,
    public_token_screener_preview as platform_token_screener_preview,
    what_changed as platform_what_changed,
)

settings = get_settings()
stripe.api_key = settings.stripe_secret_key or None

app = FastAPI(title='Hyper Wallet Tracker SaaS API')
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_site_url, 'http://localhost:3000'],
    allow_origin_regex=r'https://.*(onrender\.com|pages\.dev|copycat\.hl|copycat\.trade|copycat\.app)$',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def copycat_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith('/api/'):
        return response

    free_mode = os.getenv('COPYCAT_FREE_MODE', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}
    path = request.url.path

    # Customer/public responses can be briefly cached to cut Supabase/Render egress.
    # Authenticated/private endpoints stay no-store.
    if free_mode and request.method == 'GET' and (
        path in {'/api/dashboard-feed', '/api/dashboard-tick', '/api/performance-index'}
        or path.startswith('/api/data/v1/public/')
        or path.startswith('/api/public/')
        or path.startswith('/api/token-icons')
    ):
        if path == '/api/dashboard-tick':
            ttl = int(os.getenv('COPYCAT_DASHBOARD_TICK_CACHE_SECONDS', '12'))
        elif path == '/api/dashboard-feed':
            ttl = int(os.getenv('COPYCAT_DASHBOARD_FEED_CACHE_SECONDS', '45'))
        elif path == '/api/performance-index':
            ttl = int(os.getenv('COPYCAT_PERFORMANCE_CACHE_SECONDS', '300'))
        elif path.startswith('/api/token-icons'):
            ttl = int(os.getenv('COPYCAT_TOKEN_ICON_CACHE_SECONDS', '86400'))
        else:
            ttl = int(os.getenv('COPYCAT_PUBLIC_API_CACHE_SECONDS', '300'))
        response.headers['Cache-Control'] = f'public, max-age={ttl}, stale-while-revalidate={ttl * 2}'
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    response.headers['X-Copycat-Free-Mode'] = '1' if free_mode else '0'
    return response

@app.get('/health')
def health():
    """Render liveness check.

    This endpoint must not depend on Supabase/Postgres. When Supabase is
    recovering, over egress, or temporarily refusing connections, Render still
    needs a 200 response so the API container can finish deploying. Use
    /db-health when we specifically want to test the database connection.
    """
    return {'status': 'ok', 'service': 'hwt-api', 'database': 'not_checked'}


@app.get('/db-health')
def db_health():
    """Database readiness check for internal troubleshooting."""
    try:
        row = fetch_one('SELECT now() AS now')
        return {'status': 'ok', 'database': bool(row)}
    except Exception as exc:
        return {'status': 'degraded', 'database': False, 'message': 'database connection unavailable'}



@app.get('/api/me')
def me(user: dict = Depends(get_current_user)):
    return user


@app.get('/api/data/v1/status')
def copycat_data_api_status():
    return data_api_status()


@app.get('/api/data/v1/public/platform-health')
def copycat_platform_health():
    return platform_health_payload()


@app.post('/api/data/v1/admin/migrate-platform')
def copycat_platform_migrate(user: dict = Depends(require_active_subscription)):
    return ensure_platform_tables_once()


@app.get('/api/data/v1/public/coverage-preview')
def copycat_coverage_preview():
    return platform_coverage_preview()


@app.get('/api/data/v1/public/leaderboard-preview')
def copycat_public_leaderboard_preview(limit: int = 25):
    return platform_leaderboard_preview(limit)


@app.get('/api/data/v1/public/token-screener-preview')
def copycat_public_token_screener_preview(limit: int = 100):
    return platform_token_screener_preview(limit)


@app.get('/api/data/v1/public/asset/{coin}')
def copycat_public_asset_detail(coin: str):
    return {'status': 'ok', 'data': platform_asset_detail(coin)}


@app.get('/api/data/v1/public/asset-details')
def copycat_public_asset_details(symbols: str = ''):
    return platform_asset_details(symbols)


@app.get('/api/data/v1/public/what-changed')
def copycat_public_what_changed(limit: int = 12):
    return platform_what_changed(limit)


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


@app.get('/api/data/v1/public/leaderboard-preview')
def copycat_data_api_public_leaderboard_preview(limit: int = 20):
    return {'status': 'ok', 'data': leaderboard_preview(limit)}


@app.get('/api/data/v1/public/token-screener-preview')
def copycat_data_api_public_token_screener_preview(limit: int = 20):
    return {'status': 'ok', 'data': token_screener_preview(limit)}


@app.get('/api/data/v1/coverage')
def copycat_data_api_coverage(api_key: dict = Depends(require_copycat_api_key)):
    return quality_snapshot()


@app.get('/api/data/v1/leaderboard-v2')
def copycat_data_api_leaderboard_v2(
    limit: int = 50,
    offset: int = 0,
    min_account_value_usd: float = 0,
    qualified_only: bool = True,
    api_key: dict = Depends(require_copycat_api_key),
):
    return leaderboard_v2(limit=limit, offset=offset, min_account_value_usd=min_account_value_usd, qualified_only=qualified_only)


@app.get('/api/data/v1/token-screener')
def copycat_data_api_token_screener(limit: int = 100, api_key: dict = Depends(require_copycat_api_key)):
    return token_screener(limit=limit)


@app.get('/api/data/v1/wallet-universe')
def copycat_data_api_wallet_universe(limit: int = 500, offset: int = 0, api_key: dict = Depends(require_copycat_api_key)):
    return wallet_universe(limit=limit, offset=offset)


@app.get('/api/data/v1/historical-fills')
def copycat_data_api_historical_fills(
    wallet: str | None = None,
    coin: str | None = None,
    limit: int = 500,
    before_ts_ms: int | None = None,
    api_key: dict = Depends(require_copycat_api_key),
):
    return {'status': 'ok', 'data': historical_fills(wallet=wallet, coin=coin, limit=limit, before_ts_ms=before_ts_ms)}


@app.get('/api/data/v1/backfill-coverage')
def copycat_data_api_backfill_coverage(api_key: dict = Depends(require_copycat_api_key)):
    return backfill_coverage()


_DASHBOARD_FEED_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_DASHBOARD_FEED_LOCK = threading.Lock()
_DASHBOARD_FEED_TTL_SECONDS = float(os.getenv('COPYCAT_DASHBOARD_FEED_CACHE_SECONDS', '45'))
_LIVE_SIGNAL_ROWS_CACHE: dict[str, Any] = {'ts': 0.0, 'rows': []}
_LIVE_SIGNAL_ROWS_CACHE_TTL_SECONDS = 8.0
_DASHBOARD_TICK_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_DASHBOARD_TICK_LOCK = threading.Lock()
_DASHBOARD_TICK_TTL_SECONDS = 0.75
_DASHBOARD_TRUTH_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_DASHBOARD_TRUTH_CACHE_TTL_SECONDS = 30.0


def _public_dashboard_user() -> dict[str, Any]:
    return {'sub': 'public-dashboard', 'email': None, 'demo': True}


def _round_float(value: Any, digits: int = 6) -> float:
    return round(_safe_float(value), digits)


def _round_usd(value: Any) -> float:
    return round(_safe_float(value), 2)


def _compact_summary(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row or {})
    for key in ('tracked_account_value_usd', 'largest_account_value_usd', 'tracked_open_position_value_usd'):
        if key in out:
            out[key] = _round_usd(out.get(key))
    if out.get('markets_monitored') is None:
        try:
            out['markets_monitored'] = len(_hl_asset_universe())
        except Exception:
            out['markets_monitored'] = None
    return out


def _compact_signal_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'coin': row.get('coin'),
        'ts_ms': row.get('ts_ms'),
        'signal': _round_float(row.get('signal')),
        'confidence': row.get('confidence'),
        'wallets_long': int(row.get('wallets_long') or 0),
        'wallets_short': int(row.get('wallets_short') or 0),
        'value_long_usd': _round_usd(row.get('value_long_usd')),
        'value_short_usd': _round_usd(row.get('value_short_usd')),
        'net_value_usd': _round_usd(row.get('net_value_usd')),
        'value_long_pct_total': _round_float(row.get('value_long_pct_total')),
        'value_short_pct_total': _round_float(row.get('value_short_pct_total')),
        'live_state': bool(row.get('live_state')),
    }


def _compact_flow_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'coin': row.get('coin'),
        'net_buyer_count': int(row.get('net_buyer_count') or 0),
        'bullish_flow_usd': _round_usd(row.get('bullish_flow_usd') or row.get('bullish_value_flow_usd')),
        'bearish_flow_usd': _round_usd(row.get('bearish_flow_usd') or row.get('bearish_value_flow_usd')),
        'net_value_flow_usd': _round_usd(row.get('net_value_flow_usd')),
    }


def _compact_target_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'ts_ms': row.get('ts_ms'),
        'coin': row.get('coin'),
        'target_weight': _round_float(row.get('target_weight')),
        'index_weight': _round_float(row.get('index_weight')),
        'direction': row.get('direction'),
    }


def _compact_order_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        'ts_ms': row.get('ts_ms'),
        'wallet': row.get('wallet'),
        'wallet_label': row.get('wallet_label'),
        'coin': row.get('coin'),
        'side': row.get('side'),
        'delta_value_usd': _round_usd(row.get('delta_value_usd') or row.get('notional_usd')),
        'position_value_usd': _round_usd(row.get('position_value_usd')),
        'source': row.get('source'),
    }


def _compact_insight(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row or {})
    for key in ('value', 'net_value_flow_usd', 'bullish_value_flow_usd', 'bearish_value_flow_usd'):
        if key in out:
            out[key] = _round_usd(out.get(key))
    return out


@app.get('/api/dashboard-tick')
def dashboard_tick():
    """Tiny public payload for 1s UI refreshes.

    The heavy dashboard tables should not be downloaded and parsed every second.
    This endpoint keeps the live tape and headline numbers moving while the full
    feed refreshes less often.
    """
    now = time.time()
    cached = _DASHBOARD_TICK_CACHE.get('data')
    if cached and now - float(_DASHBOARD_TICK_CACHE.get('ts') or 0) < _DASHBOARD_TICK_TTL_SECONDS:
        return cached
    with _DASHBOARD_TICK_LOCK:
        now = time.time()
        cached = _DASHBOARD_TICK_CACHE.get('data')
        if cached and now - float(_DASHBOARD_TICK_CACHE.get('ts') or 0) < _DASHBOARD_TICK_TTL_SECONDS:
            return cached
        public_user = _public_dashboard_user()
        summary_row = _compact_summary(summary(public_user))
        order_rows = recent_orders(limit=50, user=public_user)
        data = {
            'summary': summary_row,
            'orders': [_compact_order_row(r) for r in order_rows],
            'truth': _dashboard_truth_payload(summary_row),
            'server_time_ms': _now_ms(),
            'cache_ttl_ms': int(_DASHBOARD_TICK_TTL_SECONDS * 1000),
            'public_readonly': True,
        }
        _DASHBOARD_TICK_CACHE['ts'] = time.time()
        _DASHBOARD_TICK_CACHE['data'] = data
        return data


@app.get('/api/dashboard-feed')
def dashboard_feed():
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
            # Public read-only dashboard payload. This is the heavier table
            # payload, so it is compacted and cached for several seconds. The
            # frontend uses /api/dashboard-tick for the 1s tape/headline updates.
            public_user = _public_dashboard_user()
            signal_rows = signals(limit=500, user=public_user)
            flow_rows = flow(limit=500, user=public_user)
            target_rows = targets(public_user)
            order_rows = recent_orders(limit=50, user=public_user)
            insight_result = insights(public_user)
            compact_summary = _compact_summary(summary(public_user))
            compact_signals = [_compact_signal_row(r) for r in signal_rows]
            compact_flow = [_compact_flow_row(r) for r in flow_rows]
            compact_orders = [_compact_order_row(r) for r in order_rows]
            feed = {
                'summary': compact_summary,
                'signals': compact_signals,
                'targets': [_compact_target_row(r) for r in target_rows],
                'flow': compact_flow,
                'orders': compact_orders,
                'insights': [_compact_insight(r) for r in ((insight_result.get('insights') if isinstance(insight_result, dict) else []) or [])],
                'truth': _dashboard_truth_payload(compact_summary),
                'audit': _dashboard_consistency_payload(compact_summary, compact_signals, compact_flow, compact_orders),
                'server_time_ms': _now_ms(),
                'cache_ttl_ms': int(_DASHBOARD_FEED_TTL_SECONDS * 1000),
                'public_readonly': True,
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


def _dashboard_truth_payload(summary_row: dict[str, Any] | None = None) -> dict[str, Any]:
    now = time.time()
    cached = _DASHBOARD_TRUTH_CACHE.get('data')
    if isinstance(cached, dict) and now - float(_DASHBOARD_TRUTH_CACHE.get('ts') or 0) < _DASHBOARD_TRUTH_CACHE_TTL_SECONDS:
        truth = dict(cached)
    else:
        try:
            truth = owned_universe_stats()
        except Exception as exc:
            truth = {
                'source': 'hyperliquid_native',
                'external_paid_data_required': False,
                'known_wallet_candidates': None,
                'owned_wallets_indexed': None,
                'top_claim_ready': False,
                'ranking_scope_label': 'Copycat-ranked wallets from the indexed Hyperliquid universe',
                'guarded_claim_label': 'Copycat-ranked wallets from the indexed Hyperliquid universe',
                'error': str(exc)[:180],
            }
        _DASHBOARD_TRUTH_CACHE['ts'] = time.time()
        _DASHBOARD_TRUTH_CACHE['data'] = dict(truth)
    if summary_row:
        truth['active_copycat_ranked_wallets'] = int(summary_row.get('qualified_wallets') or truth.get('active_copycat_ranked_wallets') or 0)
        truth['live_wallets'] = int(summary_row.get('live_wallets') or 0)
        truth['snapshot_wallets'] = int(summary_row.get('snapshot_wallets') or 0)
        truth['markets_monitored'] = int(summary_row.get('markets_monitored') or 0)
    return truth


def _dashboard_consistency_payload(
    summary_row: dict[str, Any] | None = None,
    signal_rows: list[dict[str, Any]] | None = None,
    flow_rows: list[dict[str, Any]] | None = None,
    order_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary_row = summary_row or _compact_summary(summary(_public_dashboard_user()))
    signal_rows = signal_rows if signal_rows is not None else [_compact_signal_row(r) for r in signals(limit=500, user=_public_dashboard_user())]
    flow_rows = flow_rows if flow_rows is not None else [_compact_flow_row(r) for r in flow(limit=500, user=_public_dashboard_user())]
    order_rows = order_rows if order_rows is not None else [_compact_order_row(r) for r in recent_orders(limit=50, user=_public_dashboard_user())]
    truth = _dashboard_truth_payload(summary_row)
    active_wallets = int(summary_row.get('qualified_wallets') or 0)
    live_wallets = int(summary_row.get('live_wallets') or 0)
    snapshot_wallets = int(summary_row.get('snapshot_wallets') or 0)
    min_live_wallets = _live_min_wallets(active_wallets) if active_wallets else 0
    signal_assets = {_normalise_index_symbol(r.get('coin')) for r in signal_rows if r.get('coin')}
    flow_assets = {_normalise_index_symbol(r.get('coin')) for r in flow_rows if r.get('coin')}
    order_assets = {_normalise_index_symbol(r.get('coin')) for r in order_rows if r.get('coin')}
    known_assets = signal_assets | flow_assets | set(_hl_asset_universe())
    missing_order_assets = sorted(a for a in order_assets if a and a not in known_assets)
    open_total = _safe_float(summary_row.get('tracked_open_position_value_usd'))
    signal_total = sum(_safe_float(r.get('value_long_usd')) + _safe_float(r.get('value_short_usd')) for r in signal_rows)
    checks = []
    def add(name: str, ok: bool, detail: str, severity: str = 'error'):
        checks.append({'name': name, 'status': 'pass' if ok else 'fail', 'severity': severity, 'detail': detail})
    add('LegacyExternalProvider disabled for live path', truth.get('external_paid_data_required') is False, 'source=hyperliquid_native')
    add('Ranking label is scoped honestly', bool(truth.get('top_claim_ready')) or 'indexed' in str(truth.get('ranking_scope_label') or '').lower(), str(truth.get('ranking_scope_label') or ''))
    add('Active cohort count', active_wallets == int(settings.qualified_wallet_limit or 50), f'{active_wallets}/{settings.qualified_wallet_limit}', 'warning')
    add('Live wallet coverage', live_wallets >= min_live_wallets if active_wallets else False, f'{live_wallets}/{active_wallets} live, {snapshot_wallets} snapshot fallback, required={min_live_wallets}', 'warning')
    add('Recent order assets mapped', not missing_order_assets, 'missing=' + ','.join(missing_order_assets[:12]) if missing_order_assets else 'all recent order assets exist in signal/flow/universe')
    add('Open exposure represented', signal_total > 0 and open_total > 0, f'signal_gross={round(signal_total,2)}; open_total={round(open_total,2)}', 'warning')
    errors = [c for c in checks if c['status'] == 'fail' and c.get('severity') == 'error']
    warnings = [c for c in checks if c['status'] == 'fail' and c.get('severity') != 'error']
    status = 'fail' if errors else 'warning' if warnings else 'pass'
    return {
        'status': status,
        'message': 'Dashboard data is synced' if status == 'pass' else 'Dashboard data has warnings' if status == 'warning' else 'Dashboard data needs attention',
        'checks': checks,
        'truth': truth,
        'missing_recent_order_assets': missing_order_assets,
        'server_time_ms': _now_ms(),
    }


@app.get('/api/dashboard-consistency')
def dashboard_consistency():
    return _dashboard_consistency_payload()


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

    live_rollup = _live_wallet_state_rollup()
    live_state_active = bool(live_rollup)
    if live_rollup:
        total_value = {
            'total': live_rollup.get('total') or 0,
            'largest_account_value_usd': live_rollup.get('largest_account_value_usd') or 0,
        }
        open_value = {
            'total': live_rollup.get('open_total') or 0,
            'positions': live_rollup.get('positions') or 0,
        }
        live_rows_for_count = _live_signal_rows(500)
        if live_rows_for_count:
            active_signal_count = sum(
                1
                for r in live_rows_for_count
                if (_safe_float(r.get('value_long_usd')) + _safe_float(r.get('value_short_usd'))) > 0
            )
            assets = {'n': active_signal_count or len(live_rows_for_count)}
        else:
            universe_count = len(_hl_asset_universe())
            assets = {'n': universe_count or int(assets.get('n') or 0)}

    latest_pos_ts = fetch_one('SELECT max(ts_ms) AS ts_ms FROM positions') or {'ts_ms': None}
    latest_run = fetch_one("SELECT ts_ms,status,message FROM collector_runs WHERE run_type='collect_once' ORDER BY ts_ms DESC LIMIT 1") or {}
    collector_age_seconds = None
    if latest_run.get('ts_ms'):
        collector_age_seconds = max(0, (_now_ms() - int(latest_run['ts_ms'])) / 1000)
    freshness_limit = max(90, int(settings.collector_freshness_seconds or 180))
    data_quality_ok = bool(stable_ts) and int(latest_wallets.get('n') or 0) >= 50 and (collector_age_seconds is None or collector_age_seconds <= freshness_limit)
    latest_live_state_ts_ms = live_rollup.get('latest_live_state_ts_ms') if live_rollup else None
    return {
        'latest_signal_ts_ms': stable_ts,
        'latest_position_ts_ms': latest_live_state_ts_ms or latest_pos_ts['ts_ms'],
        'latest_live_state_ts_ms': latest_live_state_ts_ms,
        'live_state_active': live_state_active,
        'live_coverage_mode': live_rollup.get('coverage_mode') if live_rollup else 'snapshot',
        'live_wallets': int(live_rollup.get('live_wallets') or 0) if live_rollup else 0,
        'snapshot_wallets': int(live_rollup.get('snapshot_wallets') or 0) if live_rollup else 0,
        'qualified_wallets': latest_wallets['n'],
        'tracked_account_value_usd': float(total_value['total'] or 0),
        'largest_account_value_usd': float(total_value.get('largest_account_value_usd') or 0),
        'tracked_open_position_value_usd': float(open_value['total'] or 0),
        'open_positions': int(open_value['positions'] or 0),
        'assets_with_signals': int(assets['n'] or 0),
        'markets_monitored': len(_hl_asset_universe()),
        **_dashboard_truth_payload(),
        'data_quality_status': 'healthy' if data_quality_ok else 'checking',
        'data_quality_age_seconds': collector_age_seconds,
        'data_quality_message': ('Live/hybrid Hyperliquid state active' if live_state_active else ('50-wallet snapshot healthy' if data_quality_ok else 'Waiting for a fresh completed collector snapshot')),
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



def _live_state_cutoff_ms() -> int:
    return _now_ms() - max(15, int(settings.live_state_max_age_seconds or 75)) * 1000


def _live_min_wallets(active_wallets: int) -> int:
    ratio = max(0.1, min(float(settings.live_signal_min_coverage_ratio or 0.8), 1.0))
    return max(1, int((active_wallets * ratio) + 0.999))


def _live_state_coverage() -> dict[str, int]:
    try:
        row = fetch_one('''
            WITH active AS (
              SELECT wallet FROM qualified_wallets WHERE status='active'
            )
            SELECT count(*) AS active_wallets,
                   count(s.wallet) FILTER (WHERE s.ts_ms >= :fresh_cutoff) AS fresh_wallets
            FROM active a
            LEFT JOIN copycat_live_wallet_states s ON lower(s.wallet)=lower(a.wallet)
        ''', {'fresh_cutoff': _live_state_cutoff_ms()}) or {}
        return {
            'active_wallets': int(row.get('active_wallets') or 0),
            'fresh_wallets': int(row.get('fresh_wallets') or 0),
        }
    except Exception:
        return {'active_wallets': 0, 'fresh_wallets': 0}


def _live_state_is_ready() -> bool:
    cov = _live_state_coverage()
    active = int(cov.get('active_wallets') or 0)
    fresh = int(cov.get('fresh_wallets') or 0)
    return bool(active and fresh >= _live_min_wallets(active))


def _active_wallet_addresses() -> list[str]:
    try:
        rows = fetch_all("""
            SELECT lower(wallet) AS wallet
            FROM qualified_wallets
            WHERE status='active' AND wallet ~* '^0x[0-9a-f]{40}$'
            ORDER BY rank ASC NULLS LAST, qualified_at_ms DESC NULLS LAST
        """)
        return [str(r.get('wallet') or '').lower() for r in rows if r.get('wallet')]
    except Exception:
        return []


def _latest_completed_position_ts() -> int | None:
    row = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
    if row.get('ts_ms'):
        return int(row['ts_ms'])
    row = fetch_one('SELECT max(ts_ms) AS ts_ms FROM positions') or {'ts_ms': None}
    return int(row['ts_ms']) if row.get('ts_ms') else None


def _mark_position_value(row: dict[str, Any], mids: dict[str, float], source: str) -> dict[str, Any]:
    out = dict(row)
    sym = _normalise_index_symbol(out.get('coin'))
    size = _safe_float(out.get('size'))
    stale_value = abs(_safe_float(out.get('position_value_usd')))
    stored_mark = _safe_float(out.get('mark_px'))
    current_mark = _safe_float(mids.get(sym)) or stored_mark
    current_value = abs(size) * current_mark if abs(size) > 0 and current_mark > 0 else stale_value
    mark_delta_pnl = size * (current_mark - stored_mark) if abs(size) > 0 and stored_mark > 0 and current_mark > 0 else 0.0
    out['coin'] = sym or out.get('coin')
    out['side'] = 'short' if size < 0 or str(out.get('side')).lower().startswith('short') else 'long'
    out['current_mark_px'] = current_mark
    out['current_position_value_usd'] = current_value
    out['mark_delta_pnl_usd'] = mark_delta_pnl
    out['data_source'] = source
    return out


def _live_marked_position_rows() -> list[dict[str, Any]]:
    """Fresh live wallet positions marked to current Hyperliquid mids.

    This returns whatever fresh wallet states are available. The dashboard then
    merges these with the latest completed snapshot for wallets that have not
    been refreshed yet, so one slow wallet cannot force the whole page back into
    static snapshot mode.
    """
    try:
        ensure_copycat_data_api()
        rows = fetch_all("""
            SELECT lower(lp.wallet) AS wallet,
                   upper(lp.coin) AS coin,
                   lower(lp.side) AS side,
                   lp.ts_ms,
                   COALESCE(lp.size,0) AS size,
                   COALESCE(lp.position_value_usd,0) AS position_value_usd,
                   COALESCE(lp.mark_px,
                            CASE WHEN abs(COALESCE(lp.size,0)) > 0
                                 THEN abs(COALESCE(lp.position_value_usd,0)) / abs(COALESCE(lp.size,0))
                                 ELSE NULL END) AS mark_px,
                   COALESCE(lp.entry_px,0) AS entry_px,
                   COALESCE(lp.unrealized_pnl_usd,0) AS unrealized_pnl_usd
            FROM copycat_live_positions lp
            JOIN copycat_live_wallet_states s ON lower(s.wallet)=lower(lp.wallet)
            JOIN qualified_wallets q ON lower(q.wallet)=lower(lp.wallet) AND q.status='active'
            WHERE s.ts_ms >= :fresh_cutoff
              AND lp.ts_ms >= :fresh_cutoff
              AND upper(lp.coin) NOT IN ('USDC','USDC/CASH','CASH','USD')
        """, {'fresh_cutoff': _live_state_cutoff_ms()})
    except Exception:
        return []
    mids = _hl_all_mids()
    return [_mark_position_value(dict(r), mids, 'live') for r in rows]


def _snapshot_marked_position_rows(exclude_wallets: set[str] | None = None) -> list[dict[str, Any]]:
    ts = _latest_completed_position_ts()
    if not ts:
        return []
    exclude_wallets = {str(w).lower() for w in (exclude_wallets or set()) if w}
    params: dict[str, Any] = {'ts': ts}
    exclude_sql = ''
    if exclude_wallets:
        names = []
        for i, wallet in enumerate(sorted(exclude_wallets)):
            key = f'exw{i}'
            params[key] = wallet
            names.append(f':{key}')
        exclude_sql = f"AND lower(p.wallet) NOT IN ({','.join(names)})"
    try:
        rows = fetch_all(f"""
            SELECT lower(p.wallet) AS wallet,
                   upper(p.coin) AS coin,
                   lower(p.side) AS side,
                   p.ts_ms,
                   COALESCE(p.size,0) AS size,
                   COALESCE(p.position_value_usd,0) AS position_value_usd,
                   COALESCE(p.mark_px,
                            CASE WHEN abs(COALESCE(p.size,0)) > 0
                                 THEN abs(COALESCE(p.position_value_usd,0)) / abs(COALESCE(p.size,0))
                                 ELSE NULL END) AS mark_px,
                   COALESCE(p.entry_px,0) AS entry_px,
                   COALESCE(p.unrealized_pnl_usd,0) AS unrealized_pnl_usd
            FROM positions p
            JOIN qualified_wallets q ON lower(q.wallet)=lower(p.wallet) AND q.status='active'
            WHERE p.ts_ms=:ts
              AND upper(p.coin) NOT IN ('USDC','USDC/CASH','CASH','USD')
              {exclude_sql}
        """, params)
    except Exception:
        return []
    mids = _hl_all_mids()
    return [_mark_position_value(dict(r), mids, 'snapshot_marked') for r in rows]


def _hybrid_marked_position_rows() -> list[dict[str, Any]]:
    live_rows = _live_marked_position_rows()
    live_wallets = {str(r.get('wallet') or '').lower() for r in live_rows if r.get('wallet')}
    snapshot_rows = _snapshot_marked_position_rows(exclude_wallets=live_wallets)
    return live_rows + snapshot_rows


def _live_event_flow_map() -> dict[str, dict[str, Any]]:
    try:
        rows = fetch_all("""
            SELECT upper(coin) AS coin,
                   lower(COALESCE(direction,'')) AS direction,
                   upper(COALESCE(side,'')) AS side,
                   wallet,
                   COALESCE(notional_usd,0) AS notional_usd
            FROM copycat_live_events
            WHERE ts_ms >= :flow_cutoff
              AND coin IS NOT NULL
        """, {'flow_cutoff': _now_ms() - int(settings.signal_lookback_minutes or 60) * 60_000})
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        coin = _normalise_index_symbol(r.get('coin'))
        if not coin or _index_is_margin_symbol(coin):
            continue
        d = str(r.get('direction') or '').lower()
        side = str(r.get('side') or '').upper()
        notional = _safe_float(r.get('notional_usd'))
        wallet = str(r.get('wallet') or '').lower()
        bullish = (
            ('open long' in d) or ('add long' in d) or ('close short' in d) or ('reduce short' in d) or
            (not d and side in ('B', 'BUY'))
        )
        bearish = (
            ('open short' in d) or ('add short' in d) or ('close long' in d) or ('reduce long' in d) or
            (not d and side in ('A', 'ASK', 'SELL'))
        )
        bucket = out.setdefault(coin, {'coin': coin, 'bullish_wallets': set(), 'bearish_wallets': set(), 'bullish_value_flow_usd': 0.0, 'bearish_value_flow_usd': 0.0})
        if bullish:
            bucket['bullish_wallets'].add(wallet)
            bucket['bullish_value_flow_usd'] += notional
        elif bearish:
            bucket['bearish_wallets'].add(wallet)
            bucket['bearish_value_flow_usd'] += notional
    final: dict[str, dict[str, Any]] = {}
    for coin, b in out.items():
        bullish_wallets = b.get('bullish_wallets') or set()
        bearish_wallets = b.get('bearish_wallets') or set()
        bullish_value = _safe_float(b.get('bullish_value_flow_usd'))
        bearish_value = _safe_float(b.get('bearish_value_flow_usd'))
        final[coin] = {
            'coin': coin,
            'net_buyer_count': len(bullish_wallets) - len(bearish_wallets),
            'bullish_value_flow_usd': bullish_value,
            'bearish_value_flow_usd': bearish_value,
            'bullish_flow_usd': bullish_value,
            'bearish_flow_usd': bearish_value,
            'net_value_flow_usd': bullish_value - bearish_value,
        }
    return final


def _live_wallet_state_rollup() -> dict[str, Any] | None:
    """Hybrid live rollup for all active wallets.

    Fresh live wallet states are used first. For wallets that have not refreshed
    yet, the latest completed collector snapshot is used and its open positions
    are marked to current Hyperliquid mids. This keeps the whole dashboard
    internally synced instead of showing live orders with static exposure cards.
    """
    active_wallets = _active_wallet_addresses()
    active_set = set(active_wallets)
    if not active_wallets:
        return None

    by_wallet: dict[str, dict[str, float]] = {
        w: {'account': 0.0, 'open': 0.0, 'positions': 0.0, 'adjustment': 0.0, 'source_live': 0.0}
        for w in active_wallets
    }
    latest_ts = 0
    fresh_wallets: set[str] = set()

    try:
        states = fetch_all("""
            SELECT lower(s.wallet) AS wallet,
                   s.ts_ms,
                   COALESCE(s.account_value_usd,0) AS account_value_usd
            FROM copycat_live_wallet_states s
            JOIN qualified_wallets q ON lower(q.wallet)=lower(s.wallet) AND q.status='active'
            WHERE s.ts_ms >= :fresh_cutoff
        """, {'fresh_cutoff': _live_state_cutoff_ms()})
    except Exception:
        states = []

    for srow in states:
        wallet = str(srow.get('wallet') or '').lower()
        if wallet not in active_set:
            continue
        latest_ts = max(latest_ts, int(srow.get('ts_ms') or 0))
        by_wallet[wallet]['account'] = _safe_float(srow.get('account_value_usd'))
        by_wallet[wallet]['source_live'] = 1.0
        fresh_wallets.add(wallet)

    snapshot_ts = _latest_completed_position_ts()
    if snapshot_ts:
        params: dict[str, Any] = {'ts': snapshot_ts}
        exclude_sql = ''
        if fresh_wallets:
            keys = []
            for i, wallet in enumerate(sorted(fresh_wallets)):
                key = f'fw{i}'
                params[key] = wallet
                keys.append(f':{key}')
            exclude_sql = f"AND lower(ws.wallet) NOT IN ({','.join(keys)})"
        try:
            snaps = fetch_all(f"""
                SELECT lower(ws.wallet) AS wallet,
                       ws.ts_ms,
                       COALESCE(ws.account_value_usd,0) AS account_value_usd
                FROM wallet_snapshots ws
                JOIN qualified_wallets q ON lower(q.wallet)=lower(ws.wallet) AND q.status='active'
                WHERE ws.ts_ms=:ts
                  {exclude_sql}
            """, params)
        except Exception:
            snaps = []
        for snap in snaps:
            wallet = str(snap.get('wallet') or '').lower()
            if wallet not in by_wallet:
                continue
            latest_ts = max(latest_ts, int(snap.get('ts_ms') or 0))
            by_wallet[wallet]['account'] = _safe_float(snap.get('account_value_usd'))

    positions = _hybrid_marked_position_rows()
    for p in positions:
        wallet = str(p.get('wallet') or '').lower()
        bucket = by_wallet.get(wallet)
        if not bucket:
            continue
        bucket['open'] += _safe_float(p.get('current_position_value_usd'))
        bucket['positions'] += 1
        bucket['adjustment'] += _safe_float(p.get('mark_delta_pnl_usd'))
        latest_ts = max(latest_ts, int(p.get('ts_ms') or 0))

    account_values = [max(0.0, v['account'] + v['adjustment']) for v in by_wallet.values()]
    if not account_values:
        return None
    return {
        'active_wallets': len(active_wallets),
        'live_wallets': len(fresh_wallets),
        'snapshot_wallets': max(0, len(active_wallets) - len(fresh_wallets)),
        'latest_live_state_ts_ms': latest_ts or None,
        'total': sum(account_values),
        'largest_account_value_usd': max(account_values) if account_values else 0.0,
        'open_total': sum(v['open'] for v in by_wallet.values()),
        'positions': int(sum(v['positions'] for v in by_wallet.values())),
        'coverage_mode': 'live_hybrid' if fresh_wallets else 'snapshot_live_marked',
    }


def _live_signal_rows(limit: int = 500) -> list[dict[str, Any]]:
    requested_limit = max(1, min(int(limit or 500), 500))
    now = time.time()
    cached_rows = _LIVE_SIGNAL_ROWS_CACHE.get('rows')
    if isinstance(cached_rows, list) and cached_rows and now - float(_LIVE_SIGNAL_ROWS_CACHE.get('ts') or 0) < _LIVE_SIGNAL_ROWS_CACHE_TTL_SECONDS:
        return cached_rows[:requested_limit]
    try:
        positions = _hybrid_marked_position_rows()
        flow_map = _live_event_flow_map()
        asset_universe = _hl_asset_universe()
        rollup = _live_wallet_state_rollup() or {}
    except Exception:
        return []
    if not positions and not flow_map and not asset_universe:
        return []
    gross = 0.0
    agg: dict[str, dict[str, Any]] = {}
    latest_ts = 0
    for p in positions:
        coin = _normalise_index_symbol(p.get('coin'))
        if not coin or _index_is_margin_symbol(coin):
            continue
        value = _safe_float(p.get('current_position_value_usd'))
        if value <= 0:
            continue
        wallet = str(p.get('wallet') or '').lower()
        side = str(p.get('side') or '').lower()
        row = agg.setdefault(coin, {
            'coin': coin,
            'ts_ms': 0,
            'value_long_usd': 0.0,
            'value_short_usd': 0.0,
            'wallets_long_set': set(),
            'wallets_short_set': set(),
        })
        row['ts_ms'] = max(int(row.get('ts_ms') or 0), int(p.get('ts_ms') or 0))
        latest_ts = max(latest_ts, int(p.get('ts_ms') or 0))
        gross += value
        if side.startswith('short'):
            row['value_short_usd'] += value
            row['wallets_short_set'].add(wallet)
        else:
            row['value_long_usd'] += value
            row['wallets_long_set'].add(wallet)

    # Keep the dashboard fast by returning assets with tracked-wallet
    # exposure or fresh order flow. The full Hyperliquid market count is still
    # exposed as summary.markets_monitored; zero-exposure markets should not be
    # pushed through the 1s dashboard feed.
    for coin in sorted(set(flow_map.keys())):
        agg.setdefault(coin, {
            'coin': coin,
            'ts_ms': latest_ts or _now_ms(),
            'value_long_usd': 0.0,
            'value_short_usd': 0.0,
            'wallets_long_set': set(),
            'wallets_short_set': set(),
        })

    out: list[dict[str, Any]] = []
    tracked_value = _safe_float(rollup.get('total'))
    for coin, row in agg.items():
        long_v = _safe_float(row.get('value_long_usd'))
        short_v = _safe_float(row.get('value_short_usd'))
        total = long_v + short_v
        net = long_v - short_v
        signal = net / total if total > 0 else 0.0
        confidence = 'High' if total > 0 and abs(signal) >= 0.65 else 'Medium' if total > 0 and abs(signal) >= 0.35 else 'Low'
        flow = flow_map.get(coin, {})
        out.append({
            'coin': coin,
            'ts_ms': row.get('ts_ms') or latest_ts or _now_ms(),
            'signal': signal,
            'confidence': confidence,
            'wallets_long': len(row.get('wallets_long_set') or set()),
            'wallets_short': len(row.get('wallets_short_set') or set()),
            'wallets_flat': 0,
            'value_long_usd': long_v,
            'value_short_usd': short_v,
            'net_value_usd': net,
            'value_long_pct_total': long_v / gross if gross > 0 else 0.0,
            'value_short_pct_total': short_v / gross if gross > 0 else 0.0,
            'net_buyer_count': int(flow.get('net_buyer_count') or 0),
            'bullish_value_flow_usd': _safe_float(flow.get('bullish_value_flow_usd')),
            'bearish_value_flow_usd': _safe_float(flow.get('bearish_value_flow_usd')),
            'bullish_flow_usd': _safe_float(flow.get('bullish_flow_usd')),
            'bearish_flow_usd': _safe_float(flow.get('bearish_flow_usd')),
            'net_value_flow_usd': _safe_float(flow.get('net_value_flow_usd')),
            'total_tracked_value_usd': tracked_value,
            'live_state': True,
        })
    out.sort(key=lambda r: (
        _safe_float(r.get('value_long_usd')) + _safe_float(r.get('value_short_usd')),
        abs(_safe_float(r.get('net_value_flow_usd'))),
        1 if _normalise_index_symbol(r.get('coin')) in set(asset_universe or []) else 0,
    ), reverse=True)
    _LIVE_SIGNAL_ROWS_CACHE['ts'] = time.time()
    _LIVE_SIGNAL_ROWS_CACHE['rows'] = out[:500]
    return out[:requested_limit]

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
    live_rows = _live_signal_rows(limit)
    if live_rows:
        return live_rows
    return fetch_all(
        """
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
        SELECT *, false AS live_state FROM asset_signals
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
    # At-a-glance trader/analyst insights. Prefer fresh Hyperliquid live-state
    # rows when the live worker has enough wallet coverage; otherwise fall back
    # to the last completed collector snapshot.
    rows = _live_signal_rows(500)
    ts = max([int(r.get('ts_ms') or 0) for r in rows], default=None) if rows else None
    if not rows:
        ts_row = fetch_one('SELECT max(ts_ms) AS ts_ms FROM asset_signals') or {'ts_ms': None}
        ts = ts_row.get('ts_ms')
        if not ts:
            return {'status': 'empty', 'insights': []}
        rows = fetch_all("""
            SELECT coin, signal, confidence, wallets_long, wallets_short,
                   value_long_usd, value_short_usd, net_value_usd,
                   net_buyer_count, bullish_value_flow_usd, bearish_value_flow_usd,
                   net_value_flow_usd, total_tracked_value_usd, false AS live_state
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
            {'type': 'accumulation', 'label': 'Recent accumulation', 'coin': accumulation.get('coin'), 'detail': f"Net flow ${float(accumulation.get('net_value_flow_usd') or 0):,.0f}", 'row': accumulation},
            {'type': 'distribution', 'label': 'Recent distribution', 'coin': distribution.get('coin'), 'detail': f"Net flow ${float(distribution.get('net_value_flow_usd') or 0):,.0f}", 'row': distribution},
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
    live_rows = _live_signal_rows(limit)
    if live_rows:
        return sorted(live_rows, key=lambda r: abs(_safe_float(r.get('net_value_flow_usd'))), reverse=True)[:limit]
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
               net_value_flow_usd,
               false AS live_state
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

def _external_icon_provider_icon_for_symbol(symbol: str) -> str | None:
    # Legal hygiene: do not fetch third-party token logo provider data at runtime.
    # The frontend uses local Copycat-owned token badge SVGs instead.
    return None


@app.get('/api/token-icons')
def token_icons(symbols: str = '', external: bool = False, limit: int = 60):
    """Return token icon overrides without blocking the dashboard.

    The frontend already has fast public CDN fallbacks for token icons. Calling
    ExternalIconProvider live for 100+ symbols during dashboard load can keep the browser
    and API busy for many seconds. Public dashboard calls now return immediately
    unless external=1 is explicitly requested.
    """
    requested = []
    max_symbols = max(1, min(int(limit or 60), 120))
    for raw in symbols.split(','):
        sym = raw.strip().upper()
        if sym and sym not in requested:
            requested.append(sym)
    requested = requested[:max_symbols]
    if not external:
        return {'icons': {}, 'external_lookup': False, 'note': 'Fast mode: frontend CDN fallbacks handle token artwork.'}
    # Manual/API callers can still request ExternalIconProvider enrichment, but keep the
    # limit low so one request cannot block the live dashboard service.
    requested = requested[:25]
    return {'icons': {sym: _external_icon_provider_icon_for_symbol(sym) for sym in requested}, 'external_lookup': True}



# -------------------------
# Copycat Live Strategy Index
# -------------------------
_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: dict[str, Any] = {'ts': 0.0, 'data': None}
_INDEX_CACHE_TTL_SECONDS = 5.0
_INDEX_WRITE_INTERVAL_MS = 60_000
_INDEX_METHOD_VERSION = 'copycat_live_index_v2_no_margin_signed_exposure'
_FEE_SLIPPAGE_RATE = 0.0015  # 15 bps round-trip buffer on rebalance turnover.
_SPX_CACHE: dict[str, Any] = {'ts': 0.0, 'price': None}
_SPX_CACHE_TTL_SECONDS = 60 * 30
_HL_MIDS_CACHE: dict[str, Any] = {'ts': 0.0, 'mids': None}
_HL_MIDS_CACHE_TTL_SECONDS = 4.0
_ASSET_UNIVERSE_CACHE: dict[str, Any] = {'ts': 0.0, 'symbols': []}
_ASSET_UNIVERSE_TTL_SECONDS = 60 * 30


def _normalise_index_symbol(symbol: str) -> str:
    s = str(symbol or '').upper().strip()
    if s in ('USDC/CASH', 'USDCCASH', 'USDCASH', 'CASH', 'USD'):
        return 'USDC'
    # Preserve colon namespaces such as HIP-3/stock-style perps (for example
    # xyz:MU). Removing the colon made recent-order assets visually mismatch
    # with signal/flow boards.
    return ''.join(ch for ch in s if ch.isalnum() or ch in (':', '-', '_'))


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
    now = time.time()
    cached = _HL_MIDS_CACHE.get('mids')
    if isinstance(cached, dict) and now - float(_HL_MIDS_CACHE.get('ts') or 0) < _HL_MIDS_CACHE_TTL_SECONDS:
        return cached
    payload = _hl_info({'type': 'allMids'})
    if not isinstance(payload, dict):
        return cached if isinstance(cached, dict) else {'USDC': 1.0}
    out: dict[str, float] = {'USDC': 1.0}
    for k, v in payload.items():
        sym = _normalise_index_symbol(k)
        px = _safe_float(v)
        if sym and px > 0:
            out[sym] = px
    _HL_MIDS_CACHE['ts'] = now
    _HL_MIDS_CACHE['mids'] = out
    return out


def _hl_asset_universe() -> list[str]:
    """All Hyperliquid perpetual markets from the official meta endpoint.

    The signal/flow boards merge this universe with Copycat's tracked-wallet
    exposure, so an asset can appear even when tracked wallets currently have
    no open exposure. That solves the visual mismatch where a recent fill asset
    exists on the tape but cannot be found anywhere else on the dashboard.
    """
    now = time.time()
    cached = _ASSET_UNIVERSE_CACHE.get('symbols')
    if isinstance(cached, list) and cached and now - float(_ASSET_UNIVERSE_CACHE.get('ts') or 0) < _ASSET_UNIVERSE_TTL_SECONDS:
        return cached
    symbols: list[str] = []
    try:
        payload = _hl_info({'type': 'meta'})
        universe = payload.get('universe') if isinstance(payload, dict) else []
        for item in universe or []:
            if not isinstance(item, dict):
                continue
            sym = _normalise_index_symbol(item.get('name') or item.get('coin') or item.get('symbol'))
            if sym and not _index_is_margin_symbol(sym) and sym not in symbols:
                symbols.append(sym)
    except Exception:
        symbols = []
    if not symbols:
        try:
            symbols = [sym for sym in _hl_all_mids().keys() if sym and not _index_is_margin_symbol(sym)]
        except Exception:
            symbols = []
    if symbols:
        symbols = sorted(set(symbols))
        _ASSET_UNIVERSE_CACHE['ts'] = now
        _ASSET_UNIVERSE_CACHE['symbols'] = symbols
    return symbols


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
    live_rows = _live_signal_rows(500)
    if live_rows:
        ts = max(int(r.get('ts_ms') or 0) for r in live_rows)
        rows = live_rows
    else:
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



def _limit_index_points(data: dict[str, Any], max_points: int | None = 240) -> dict[str, Any]:
    out = dict(data or {})
    points = list(out.get('points') or [])
    try:
        limit = int(max_points or 0)
    except Exception:
        limit = 240
    if limit > 0 and len(points) > limit:
        # Evenly sample the line while always keeping the first and last point.
        if limit <= 2:
            trimmed = [points[0], points[-1]]
        else:
            step = (len(points) - 1) / float(limit - 1)
            idxs = sorted({round(i * step) for i in range(limit)})
            trimmed = [points[i] for i in idxs if 0 <= i < len(points)]
            if trimmed[0] is not points[0]:
                trimmed.insert(0, points[0])
            if trimmed[-1] is not points[-1]:
                trimmed.append(points[-1])
        out['points'] = trimmed[:limit]
        out['points_returned'] = len(out['points'])
        out['points_total'] = len(points)
    return out

@app.get('/api/performance-index')
def performance_index(force: bool = False, max_points: int = 240):
    now = time.time()
    if not force and _INDEX_CACHE.get('data') and now - float(_INDEX_CACHE.get('ts') or 0) < _INDEX_CACHE_TTL_SECONDS:
        return _limit_index_points(_INDEX_CACHE['data'], max_points)
    with _INDEX_LOCK:
        now = time.time()
        if not force and _INDEX_CACHE.get('data') and now - float(_INDEX_CACHE.get('ts') or 0) < _INDEX_CACHE_TTL_SECONDS:
            return _limit_index_points(_INDEX_CACHE['data'], max_points)
        try:
            data = _update_strategy_index_locked(force=force)
        except Exception as exc:
            cached = _INDEX_CACHE.get('data')
            if cached:
                stale = dict(cached)
                stale['stale'] = True
                stale['warning'] = f'Performance index using last good value while live price feed reconnects: {str(exc)[:180]}'
                return _limit_index_points(stale, max_points)
            raise HTTPException(status_code=503, detail=f'Performance index is not ready: {str(exc)[:220]}') from exc
        _INDEX_CACHE['ts'] = time.time()
        _INDEX_CACHE['data'] = data
        return _limit_index_points(data, max_points)


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


@app.get('/api/data/v1/leaderboard-preview')
def copycat_data_api_public_leaderboard_preview_alias(limit: int = 20):
    return {'status': 'ok', 'data': leaderboard_preview(limit)}


@app.get('/api/data/v1/token-screener-preview')
def copycat_data_api_public_token_screener_preview_alias(limit: int = 20):
    return {'status': 'ok', 'data': token_screener_preview(limit)}

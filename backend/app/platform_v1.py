from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from typing import Any

from sqlalchemy import text

from .db import engine, fetch_all, fetch_one
from .settings import get_settings


COMMON_TOKEN_NAMES: dict[str, str] = {
    'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'HYPE': 'Hyperliquid', 'SOL': 'Solana',
    'USDC': 'USD Coin', 'USDT': 'Tether', 'BNB': 'BNB', 'XRP': 'XRP',
    'DOGE': 'Dogecoin', 'AVAX': 'Avalanche', 'LINK': 'Chainlink', 'AAVE': 'Aave',
    'SUI': 'Sui', 'NEAR': 'NEAR Protocol', 'ZEC': 'Zcash', 'TRX': 'TRON',
    'XLM': 'Stellar', 'DOT': 'Polkadot', 'LTC': 'Litecoin', 'UNI': 'Uniswap',
    'ARB': 'Arbitrum', 'OP': 'Optimism', 'PAXG': 'PAX Gold', 'FET': 'Artificial Superintelligence Alliance',
    'INJ': 'Injective', 'ATOM': 'Cosmos', 'FIL': 'Filecoin', 'APT': 'Aptos',
    'WIF': 'dogwifhat', 'FARTCOIN': 'Fartcoin', 'PUMP': 'Pump.fun',
}


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def normalise_coin(coin: str | None) -> str:
    raw = str(coin or '').upper().strip()
    if raw.startswith('XYZ:'):
        raw = raw.split(':', 1)[1]
    if raw in {'USDC/CASH', 'USDCCASH', 'USDCASH', 'CASH', 'USD'}:
        return 'USDC'
    return ''.join(ch for ch in raw if ch.isalnum()) or raw


def display_name(coin: str | None) -> str:
    sym = normalise_coin(coin)
    return COMMON_TOKEN_NAMES.get(sym, sym)


_PLATFORM_SCHEMA_READY = False


def ensure_platform_tables(conn) -> None:
    global _PLATFORM_SCHEMA_READY
    if _PLATFORM_SCHEMA_READY:
        return
    try:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("SET LOCAL statement_timeout = '20s'"))
    except Exception:
        pass
    got_lock = False
    try:
        got_lock = bool(conn.execute(text('SELECT pg_try_advisory_lock(82420601)')).scalar())
    except Exception:
        got_lock = False
    if not got_lock:
        return
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS copycat_worker_heartbeats (
              worker_name text PRIMARY KEY,
              ts_ms bigint NOT NULL,
              status text NOT NULL DEFAULT 'ok',
              message text NOT NULL DEFAULT '',
              metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
              updated_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS copycat_alert_events (
              id bigserial PRIMARY KEY,
              ts_ms bigint NOT NULL,
              alert_type text NOT NULL,
              title text NOT NULL,
              body text NOT NULL,
              channel text NOT NULL DEFAULT 'telegram',
              status text NOT NULL DEFAULT 'queued',
              metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS copycat_data_coverage_snapshots (
              id bigserial PRIMARY KEY,
              ts_ms bigint NOT NULL,
              known_wallet_candidates integer NOT NULL DEFAULT 0,
              indexed_wallets integer NOT NULL DEFAULT 0,
              qualified_wallets integer NOT NULL DEFAULT 0,
              stored_fills integer NOT NULL DEFAULT 0,
              stored_live_events integer NOT NULL DEFAULT 0,
              markets_monitored integer NOT NULL DEFAULT 0,
              top_claim_ready boolean NOT NULL DEFAULT false,
              coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS copycat_rebalance_events (
              id bigserial PRIMARY KEY,
              ts_ms bigint NOT NULL,
              source text NOT NULL DEFAULT 'copycat_index',
              summary text NOT NULL DEFAULT '',
              targets_json jsonb NOT NULL DEFAULT '[]'::jsonb,
              created_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        _PLATFORM_SCHEMA_READY = True
    finally:
        try:
            conn.execute(text('SELECT pg_advisory_unlock(82420601)'))
        except Exception:
            pass


def ensure_platform_tables_once() -> dict[str, Any]:
    with engine.begin() as conn:
        ensure_platform_tables(conn)
    return {'status': 'ok'}


def heartbeat(worker_name: str, status: str = 'ok', message: str = '', metrics: dict[str, Any] | None = None) -> None:
    try:
        with engine.begin() as conn:
            ensure_platform_tables(conn)
            conn.execute(text("""
                INSERT INTO copycat_worker_heartbeats(worker_name, ts_ms, status, message, metrics_json, updated_at)
                VALUES(:worker_name, :ts_ms, :status, :message, CAST(:metrics_json AS jsonb), now())
                ON CONFLICT(worker_name) DO UPDATE SET
                  ts_ms=excluded.ts_ms,
                  status=excluded.status,
                  message=excluded.message,
                  metrics_json=excluded.metrics_json,
                  updated_at=now()
            """), {
                'worker_name': worker_name,
                'ts_ms': now_ms(),
                'status': status[:40],
                'message': message[:500],
                'metrics_json': json.dumps(metrics or {}),
            })
    except Exception:
        pass


def _count(sql: str) -> int:
    try:
        row = fetch_one(sql) or {}
        return int(row.get('n') or 0)
    except Exception:
        return 0


def _latest_ms(table: str, column: str = 'ts_ms') -> int | None:
    try:
        row = fetch_one(f'SELECT max({column}) AS ts_ms FROM {table}') or {}
        return int(row['ts_ms']) if row.get('ts_ms') else None
    except Exception:
        return None


def coverage_preview() -> dict[str, Any]:
    settings = get_settings()
    known = _count('SELECT count(*) AS n FROM wallet_candidates')
    indexed = _count('SELECT count(*) AS n FROM owned_wallet_metrics')
    qualified = _count('SELECT count(*) AS n FROM owned_wallet_metrics WHERE qualifies=true')
    active = _count("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'")
    fills = _count('SELECT count(*) AS n FROM owned_wallet_fills')
    live_events = _count('SELECT count(*) AS n FROM copycat_live_events')
    markets = _count('SELECT count(*) AS n FROM copycat_market_universe') or _count('SELECT count(DISTINCT coin) AS n FROM asset_signals')
    min_indexed = int(getattr(settings, 'owned_top_claim_min_indexed_wallets', 10000) or 10000)
    ready = indexed >= min_indexed
    label = f"Top 50 Copycat-ranked wallets from {indexed:,} indexed / {known:,} known Hyperliquid wallets"
    return {
        'status': 'ok', 'source': 'hyperliquid_native', 'external_paid_data_required': False,
        'known_wallet_candidates': known, 'indexed_wallets': indexed, 'qualified_wallets': qualified,
        'active_ranked_wallets': active, 'stored_fills': fills, 'stored_live_events': live_events,
        'markets_monitored': markets, 'top_claim_ready': ready, 'top_claim_min_indexed_wallets': min_indexed,
        'ranking_scope_label': label, 'latest_metric_ts_ms': _latest_ms('owned_wallet_metrics'),
        'latest_fill_ts_ms': _latest_ms('owned_wallet_fills'), 'latest_live_event_ts_ms': _latest_ms('copycat_live_events'),
        'server_time_ms': now_ms(),
    }


def platform_health() -> dict[str, Any]:
    with engine.begin() as conn:
        ensure_platform_tables(conn)
        rows = conn.execute(text("""
            SELECT worker_name, ts_ms, status, message, metrics_json
            FROM copycat_worker_heartbeats
            ORDER BY worker_name
        """)).mappings().all()
    cov = coverage_preview()
    max_age_ms = int(getattr(get_settings(), 'platform_worker_heartbeat_max_age_minutes', 30) or 30) * 60_000
    worker_rows = []
    for r in rows:
        age = now_ms() - int(r.get('ts_ms') or 0)
        worker_rows.append({
            'worker_name': r.get('worker_name'),
            'status': 'stale' if age > max_age_ms else r.get('status'),
            'age_seconds': round(age / 1000, 1),
            'message': r.get('message'),
            'metrics': r.get('metrics_json') or {},
        })
    return {'status': 'ok', 'coverage': cov, 'workers': worker_rows}


def public_leaderboard_preview(limit: int = 25) -> dict[str, Any]:
    limit = max(1, min(int(limit or 25), 100))
    try:
        rows = fetch_all("""
            SELECT wallet, ts_ms, account_value_usd, total_ntl_pos_usd,
                   closed_pnl_lookback_usd, fees_lookback_usd, fills_lookback_count,
                   active_days_observed, score, qualifies
            FROM owned_wallet_metrics
            WHERE qualifies=true
            ORDER BY score DESC, account_value_usd DESC
            LIMIT :limit
        """, {'limit': limit})
    except Exception:
        rows = []
    out = []
    for i, r in enumerate(rows, 1):
        wallet = str(r.get('wallet') or '')
        out.append({
            'rank': i,
            'wallet': wallet,
            'wallet_label': f'{wallet[:6]}…{wallet[-4:]}' if len(wallet) >= 12 else wallet,
            'copycat_score': round(safe_float(r.get('score')), 2),
            'account_value_usd': round(safe_float(r.get('account_value_usd')), 2),
            'open_position_value_usd': round(safe_float(r.get('total_ntl_pos_usd')), 2),
            'realized_pnl_lookback_usd': round(safe_float(r.get('closed_pnl_lookback_usd')), 2),
            'fees_lookback_usd': round(safe_float(r.get('fees_lookback_usd')), 2),
            'fills_lookback_count': int(r.get('fills_lookback_count') or 0),
            'active_days_observed': int(r.get('active_days_observed') or 0),
            'ts_ms': r.get('ts_ms'),
        })
    return {'status': 'ok', 'scope': coverage_preview()['ranking_scope_label'], 'data': out}


def _latest_signal_rows(limit: int = 250) -> list[dict[str, Any]]:
    try:
        return fetch_all("""
            WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
            SELECT a.*
            FROM asset_signals a
            WHERE a.ts_ms=(SELECT ts_ms FROM latest)
            ORDER BY abs(a.net_value_usd) DESC NULLS LAST
            LIMIT :limit
        """, {'limit': limit})
    except Exception:
        return []


def public_token_screener_preview(limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit or 100), 250))
    out = []
    for r in _latest_signal_rows(limit=limit):
        coin = normalise_coin(r.get('coin'))
        long_usd = safe_float(r.get('value_long_usd'))
        short_usd = safe_float(r.get('value_short_usd'))
        gross = long_usd + short_usd
        if gross <= 0:
            continue
        tilt = 'long' if long_usd >= short_usd else 'short'
        conviction = max(long_usd, short_usd) / gross if gross else 0
        out.append({
            'coin': coin, 'name': display_name(coin), 'tilt': tilt,
            'conviction_pct': round(conviction * 100, 2), 'confidence': r.get('confidence'),
            'wallets_long': int(r.get('wallets_long') or 0), 'wallets_short': int(r.get('wallets_short') or 0),
            'gross_exposure_usd': round(gross, 2), 'net_exposure_usd': round(safe_float(r.get('net_value_usd')), 2),
            'score': round(conviction * gross, 2), 'ts_ms': r.get('ts_ms'),
        })
    out.sort(key=lambda x: x['score'], reverse=True)
    return {'status': 'ok', 'data': out[:limit], 'server_time_ms': now_ms()}


def _asset_price(coin: str) -> float | None:
    sym = normalise_coin(coin)
    queries = [
        ("SELECT mark_px AS px FROM copycat_market_snapshots WHERE upper(coin)=:coin AND mark_px IS NOT NULL ORDER BY ts_ms DESC LIMIT 1", {'coin': sym}),
        ("SELECT mark_px AS px FROM copycat_live_positions WHERE upper(coin)=:coin AND mark_px IS NOT NULL ORDER BY ts_ms DESC LIMIT 1", {'coin': sym}),
        ("SELECT CASE WHEN abs(size)>0 THEN abs(position_value_usd)/abs(size) ELSE NULL END AS px FROM positions WHERE upper(coin)=:coin AND abs(size)>0 ORDER BY ts_ms DESC LIMIT 1", {'coin': sym}),
    ]
    for sql, params in queries:
        try:
            px = safe_float((fetch_one(sql, params) or {}).get('px'))
            if px > 0:
                return px
        except Exception:
            pass
    return None


def asset_detail(coin: str) -> dict[str, Any]:
    sym = normalise_coin(coin)
    try:
        market = fetch_one("""
            SELECT coin, display_name, market_type, max_leverage, sz_decimals, only_isolated, is_delisted, updated_at
            FROM copycat_market_universe
            WHERE upper(coin)=:coin
            LIMIT 1
        """, {'coin': sym}) or {}
    except Exception:
        market = {}
    try:
        signal = fetch_one("""
            WITH latest AS (SELECT max(ts_ms) AS ts_ms FROM asset_signals)
            SELECT * FROM asset_signals WHERE ts_ms=(SELECT ts_ms FROM latest) AND upper(coin)=:coin LIMIT 1
        """, {'coin': sym}) or {}
    except Exception:
        signal = {}
    long_usd = safe_float(signal.get('value_long_usd'))
    short_usd = safe_float(signal.get('value_short_usd'))
    gross = long_usd + short_usd
    tilt = 'Long' if long_usd >= short_usd else 'Short'
    conviction = max(long_usd, short_usd) / gross if gross > 0 else 0
    return {
        'coin': sym, 'name': market.get('display_name') or display_name(sym), 'market_type': market.get('market_type') or 'perp',
        'current_price': _asset_price(sym), 'max_leverage': market.get('max_leverage'),
        'only_isolated': bool(market.get('only_isolated') or False), 'is_delisted': bool(market.get('is_delisted') or False),
        'tilt': tilt if gross > 0 else 'No active tilt', 'conviction_pct': round(conviction * 100, 1) if gross > 0 else 0,
        'confidence': signal.get('confidence'), 'wallets_long': int(signal.get('wallets_long') or 0),
        'wallets_short': int(signal.get('wallets_short') or 0), 'value_long_usd': round(long_usd, 2),
        'value_short_usd': round(short_usd, 2), 'gross_exposure_usd': round(gross, 2),
        'net_exposure_usd': round(safe_float(signal.get('net_value_usd')), 2),
        'net_flow_usd': round(safe_float(signal.get('net_value_flow_usd')), 2),
        'bullish_flow_usd': round(safe_float(signal.get('bullish_value_flow_usd')), 2),
        'bearish_flow_usd': round(safe_float(signal.get('bearish_value_flow_usd')), 2),
        'ts_ms': signal.get('ts_ms'),
    }


def asset_details(symbols: str = '') -> dict[str, Any]:
    tokens = []
    for part in (symbols or '').split(','):
        sym = normalise_coin(part)
        if sym and sym not in tokens:
            tokens.append(sym)
    tokens = tokens[:120]
    return {'status': 'ok', 'assets': {sym: asset_detail(sym) for sym in tokens}, 'server_time_ms': now_ms()}


def what_changed(limit: int = 12) -> dict[str, Any]:
    changes = []
    for r in _latest_signal_rows(250):
        coin = normalise_coin(r.get('coin'))
        long_usd = safe_float(r.get('value_long_usd'))
        short_usd = safe_float(r.get('value_short_usd'))
        gross = long_usd + short_usd
        if gross <= 0:
            continue
        tilt = 'long' if long_usd >= short_usd else 'short'
        conviction = max(long_usd, short_usd) / gross
        flow = safe_float(r.get('net_value_flow_usd'))
        score = abs(flow) + gross * conviction * 0.01
        if score <= 0:
            continue
        changes.append({
            'coin': coin, 'name': display_name(coin),
            'headline': f"{coin} is {round(conviction * 100)}% {tilt} across tracked exposure",
            'tilt': tilt, 'conviction_pct': round(conviction * 100, 1),
            'gross_exposure_usd': round(gross, 2), 'net_flow_usd': round(flow, 2), 'score': round(score, 2),
        })
    changes.sort(key=lambda x: x['score'], reverse=True)
    return {'status': 'ok', 'data': changes[: max(1, min(limit, 50))]}


def create_coverage_snapshot() -> dict[str, Any]:
    cov = coverage_preview()
    with engine.begin() as conn:
        ensure_platform_tables(conn)
        conn.execute(text("""
            INSERT INTO copycat_data_coverage_snapshots(
              ts_ms, known_wallet_candidates, indexed_wallets, qualified_wallets,
              stored_fills, stored_live_events, markets_monitored, top_claim_ready, coverage_json
            ) VALUES(
              :ts_ms, :known, :indexed, :qualified, :fills, :events, :markets, :ready, CAST(:coverage_json AS jsonb)
            )
        """), {
            'ts_ms': now_ms(), 'known': int(cov.get('known_wallet_candidates') or 0),
            'indexed': int(cov.get('indexed_wallets') or 0), 'qualified': int(cov.get('qualified_wallets') or 0),
            'fills': int(cov.get('stored_fills') or 0), 'events': int(cov.get('stored_live_events') or 0),
            'markets': int(cov.get('markets_monitored') or 0), 'ready': bool(cov.get('top_claim_ready')),
            'coverage_json': json.dumps(cov),
        })
    return cov


def build_15m_alert_digest() -> dict[str, Any]:
    cov = coverage_preview()
    changes = what_changed(6).get('data', [])
    lines = ['Copycat 15m update']
    for item in changes[:3]:
        direction = 'bullish' if item.get('tilt') == 'long' else 'bearish'
        lines.append(f"{item['coin']}: {item['conviction_pct']:.0f}% {direction}, exposure ${item['gross_exposure_usd']:,.0f}")
    if not changes:
        lines.append('No major tracked-wallet positioning changes detected.')
    lines.append(f"Coverage: {cov['indexed_wallets']:,} indexed / {cov['known_wallet_candidates']:,} known wallets")
    lines.append('Market intelligence only. Not financial advice.')
    return {'status': 'ok', 'title': 'Copycat 15m update', 'body': '\n'.join(lines), 'coverage': cov, 'changes': changes}


def send_telegram_digest() -> dict[str, Any]:
    settings = get_settings()
    digest = build_15m_alert_digest()
    if not getattr(settings, 'telegram_bot_token', '') or not getattr(settings, 'telegram_chat_id', ''):
        heartbeat('hwt-telegram-alerts-15m', 'skipped', 'Telegram credentials not configured', {'sent': False})
        return {'status': 'skipped', 'reason': 'telegram credentials not configured', 'digest': digest}
    text_body = digest['body'][:3900]
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = urllib.parse.urlencode({'chat_id': settings.telegram_chat_id, 'text': text_body, 'disable_web_page_preview': 'true'}).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=payload, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        heartbeat('hwt-telegram-alerts-15m', 'ok', 'Digest sent', {'sent': True})
        with engine.begin() as conn:
            ensure_platform_tables(conn)
            conn.execute(text("""
                INSERT INTO copycat_alert_events(ts_ms, alert_type, title, body, channel, status, metadata_json)
                VALUES(:ts_ms, '15m_digest', :title, :body, 'telegram', 'sent', CAST(:metadata_json AS jsonb))
            """), {'ts_ms': now_ms(), 'title': digest['title'], 'body': text_body, 'metadata_json': json.dumps({'telegram_response': raw[:500]})})
        return {'status': 'ok', 'sent': True, 'digest': digest}
    except Exception as exc:
        heartbeat('hwt-telegram-alerts-15m', 'error', str(exc)[:400], {'sent': False})
        return {'status': 'error', 'sent': False, 'error': str(exc), 'digest': digest}

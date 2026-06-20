from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any

from fastapi import Header, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine, fetch_all, fetch_one
from .settings import get_settings


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def short_wallet(wallet: str) -> str:
    wallet = wallet or ''
    return f'{wallet[:6]}…{wallet[-4:]}' if len(wallet) >= 12 else wallet


def ensure_copycat_data_api_tables(conn) -> None:
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS copycat_api_keys (
          id bigserial PRIMARY KEY,
          key_hash text NOT NULL UNIQUE,
          label text NOT NULL DEFAULT 'Copycat API key',
          owner_email text,
          plan text NOT NULL DEFAULT 'internal',
          active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          last_used_at timestamptz,
          rate_limit_per_minute integer NOT NULL DEFAULT 120,
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_api_keys_active ON copycat_api_keys(active)'))

    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS copycat_api_usage (
          id bigserial PRIMARY KEY,
          key_id bigint REFERENCES copycat_api_keys(id) ON DELETE SET NULL,
          ts_ms bigint NOT NULL,
          ts timestamptz NOT NULL DEFAULT now(),
          path text NOT NULL,
          method text NOT NULL,
          status_code integer NOT NULL DEFAULT 200,
          ip text,
          user_agent text
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_api_usage_key_ts ON copycat_api_usage(key_id, ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_api_usage_ts ON copycat_api_usage(ts_ms DESC)'))

    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS copycat_live_events (
          id bigserial PRIMARY KEY,
          event_id text NOT NULL UNIQUE,
          wallet text NOT NULL,
          event_type text NOT NULL,
          ts_ms bigint NOT NULL,
          ts timestamptz NOT NULL DEFAULT now(),
          coin text,
          side text,
          direction text,
          px double precision,
          size double precision,
          notional_usd double precision,
          closed_pnl_usd double precision,
          fee_usd double precision,
          source text NOT NULL DEFAULT 'hyperliquid_ws',
          raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_live_events_ts ON copycat_live_events(ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_live_events_wallet_ts ON copycat_live_events(wallet, ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_live_events_coin_ts ON copycat_live_events(coin, ts_ms DESC)'))

    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS copycat_historical_sources (
          id bigserial PRIMARY KEY,
          name text NOT NULL UNIQUE,
          source_type text NOT NULL,
          url text,
          legal_status text NOT NULL,
          coverage text NOT NULL,
          limitation text NOT NULL DEFAULT '',
          active boolean NOT NULL DEFAULT true,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_copycat_historical_sources_active ON copycat_historical_sources(active)'))
    conn.execute(text('''
        INSERT INTO copycat_historical_sources(name, source_type, url, legal_status, coverage, limitation, metadata_json)
        VALUES
          ('Hyperliquid official Info API', 'official_api', 'https://api.hyperliquid.xyz/info', 'official_public_api', 'Current user state, user portfolio, recent/historical user fills by time where available, funding and ledger endpoints.', 'Not a complete already-indexed Nansen-style wallet universe; Copycat must store observations permanently from collection time.', jsonb_build_object('priority', 1)),
          ('Hyperliquid official WebSocket', 'official_websocket', 'wss://api.hyperliquid.xyz/ws', 'official_public_api', 'Streaming user fills, order updates, account state and market feeds for tracked wallets.', 'Requires one subscription per tracked wallet/feed; only becomes complete for wallets once Copycat is subscribed.', jsonb_build_object('priority', 2)),
          ('Hyperliquid official archive bucket', 'official_archive', 's3://hyperliquid-archive', 'official_public_archive', 'Official historical market data such as L2 snapshots and asset contexts.', 'Official docs state this archive may be delayed/missing and does not provide every historical dataset such as all user fills.', jsonb_build_object('priority', 3))
        ON CONFLICT(name) DO UPDATE SET
          source_type=excluded.source_type,
          url=excluded.url,
          legal_status=excluded.legal_status,
          coverage=excluded.coverage,
          limitation=excluded.limitation,
          active=true,
          updated_at=now(),
          metadata_json=excluded.metadata_json
    '''))


def ensure_copycat_data_api() -> None:
    with engine.begin() as conn:
        ensure_copycat_data_api_tables(conn)


def hash_api_key(api_key: str) -> str:
    settings = get_settings()
    salt = settings.copycat_api_key_salt or settings.supabase_jwt_secret or 'copycat-local-dev'
    return hashlib.sha256(f'{salt}:{api_key}'.encode('utf-8')).hexdigest()


def generate_api_key(label: str = 'Copycat API key', owner_email: str | None = None, plan: str = 'internal') -> dict[str, Any]:
    api_key = f'cc_live_{secrets.token_urlsafe(32)}'
    key_hash = hash_api_key(api_key)
    with engine.begin() as conn:
        ensure_copycat_data_api_tables(conn)
        row = conn.execute(text('''
            INSERT INTO copycat_api_keys(key_hash,label,owner_email,plan,active,metadata_json)
            VALUES(:key_hash,:label,:owner_email,:plan,true,'{}'::jsonb)
            RETURNING id,label,owner_email,plan,created_at,rate_limit_per_minute
        '''), {'key_hash': key_hash, 'label': label[:120], 'owner_email': owner_email, 'plan': plan[:40]}).mappings().first()
    return {'api_key': api_key, 'record': dict(row or {})}


def _extract_api_key(auth_header: str | None, explicit_key: str | None) -> str | None:
    if explicit_key:
        return explicit_key.strip()
    if not auth_header:
        return None
    auth_header = auth_header.strip()
    if auth_header.lower().startswith('bearer '):
        return auth_header.split(' ', 1)[1].strip()
    return None


async def require_copycat_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_copycat_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    api_key = _extract_api_key(authorization, x_copycat_api_key)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Copycat API key required')
    key_hash = hash_api_key(api_key)
    try:
        with engine.begin() as conn:
            ensure_copycat_data_api_tables(conn)
            row = conn.execute(text('''
                SELECT id, label, owner_email, plan, active, rate_limit_per_minute
                FROM copycat_api_keys
                WHERE key_hash=:key_hash AND active=true
                LIMIT 1
            '''), {'key_hash': key_hash}).mappings().first()
            if not row:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Copycat API key')
            key = dict(row)
            window_start = now_ms() - 60_000
            used = conn.execute(text('''
                SELECT count(*) FROM copycat_api_usage
                WHERE key_id=:key_id AND ts_ms>=:window_start
            '''), {'key_id': key['id'], 'window_start': window_start}).scalar() or 0
            if int(used) >= int(key.get('rate_limit_per_minute') or 120):
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Copycat API rate limit exceeded')
            conn.execute(text('UPDATE copycat_api_keys SET last_used_at=now() WHERE id=:id'), {'id': key['id']})
            conn.execute(text('''
                INSERT INTO copycat_api_usage(key_id,ts_ms,path,method,status_code,ip,user_agent)
                VALUES(:key_id,:ts_ms,:path,:method,200,:ip,:user_agent)
            '''), {
                'key_id': key['id'],
                'ts_ms': now_ms(),
                'path': request.url.path,
                'method': request.method,
                'ip': request.client.host if request.client else None,
                'user_agent': request.headers.get('user-agent', '')[:300],
            })
            return key
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f'Copycat API key store unavailable: {str(exc)[:120]}')


def data_api_status() -> dict[str, Any]:
    ensure_copycat_data_api()
    owned = fetch_one('''
        SELECT count(*) AS wallets,
               count(*) FILTER (WHERE qualifies=true) AS qualified,
               max(ts_ms) AS latest_metric_ts_ms
        FROM owned_wallet_metrics
    ''') or {'wallets': 0, 'qualified': 0, 'latest_metric_ts_ms': None}
    events = fetch_one('SELECT count(*) AS events, max(ts_ms) AS latest_event_ts_ms FROM copycat_live_events') or {'events': 0, 'latest_event_ts_ms': None}
    fills = fetch_one('SELECT count(*) AS fills, max(ts_ms) AS latest_fill_ts_ms FROM owned_wallet_fills') or {'fills': 0, 'latest_fill_ts_ms': None}
    active = fetch_one("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'") or {'n': 0}
    return {
        'status': 'ok',
        'product': 'Copycat Data API',
        'version': 'v1',
        'source': 'hyperliquid_native',
        'nansen_required': False,
        'tracked_active_wallets': int(active.get('n') or 0),
        'owned_wallets_indexed': int(owned.get('wallets') or 0),
        'owned_wallets_qualified': int(owned.get('qualified') or 0),
        'stored_owned_fills': int(fills.get('fills') or 0),
        'stored_live_events': int(events.get('events') or 0),
        'latest_metric_ts_ms': owned.get('latest_metric_ts_ms'),
        'latest_fill_ts_ms': fills.get('latest_fill_ts_ms'),
        'latest_live_event_ts_ms': events.get('latest_event_ts_ms'),
    }


def data_api_leaderboard(limit: int = 50) -> list[dict[str, Any]]:
    ensure_copycat_data_api()
    limit = max(1, min(int(limit or 50), 250))
    rows = fetch_all('''
        SELECT wallet, ts_ms, account_value_usd, total_ntl_pos_usd,
               pnl_day_usd, pnl_30d_usd, pnl_all_time_usd,
               closed_pnl_lookback_usd, fees_lookback_usd, fills_lookback_count,
               active_days_observed, score, qualifies, metrics_json
        FROM owned_wallet_metrics
        ORDER BY qualifies DESC, score DESC, account_value_usd DESC
        LIMIT :limit
    ''', {'limit': limit})
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        metrics = row.pop('metrics_json', {}) or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        wallet = row.get('wallet') or ''
        out.append({
            'rank': i,
            'wallet': wallet,
            'wallet_label': short_wallet(wallet),
            **row,
            'score_components': metrics.get('score_components') or {},
            'disqualifiers': metrics.get('disqualifiers') or [],
            'source': 'hyperliquid_native',
        })
    return out


def data_api_wallet_profile(wallet: str) -> dict[str, Any]:
    ensure_copycat_data_api()
    wallet = (wallet or '').lower().strip()
    if not wallet.startswith('0x') or len(wallet) != 42:
        raise HTTPException(status_code=400, detail='Wallet must be a 42-character 0x address')
    metric = fetch_one('SELECT * FROM owned_wallet_metrics WHERE wallet=:wallet', {'wallet': wallet}) or {}
    active = fetch_one("SELECT rank,score,status,qualified_at_ms FROM qualified_wallets WHERE wallet=:wallet ORDER BY status='active' DESC, rank ASC LIMIT 1", {'wallet': wallet}) or {}
    exposure = fetch_all('''
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM positions WHERE wallet=:wallet)
        SELECT coin, side, position_value_usd, size, entry_px, mark_px, unrealized_pnl_usd, leverage, liquidation_px, ts_ms
        FROM positions
        WHERE wallet=:wallet AND ts_ms=(SELECT ts_ms FROM latest_ts)
        ORDER BY position_value_usd DESC
    ''', {'wallet': wallet})
    recent_fills = data_api_wallet_fills(wallet, limit=25)
    return {
        'wallet': wallet,
        'wallet_label': short_wallet(wallet),
        'source': 'hyperliquid_native',
        'qualification': active,
        'metrics': metric,
        'latest_exposure': exposure,
        'recent_fills': recent_fills,
    }


def data_api_wallet_fills(wallet: str, limit: int = 100) -> list[dict[str, Any]]:
    ensure_copycat_data_api()
    wallet = (wallet or '').lower().strip()
    limit = max(1, min(int(limit or 100), 1000))
    return fetch_all('''
        SELECT wallet, tid, ts_ms, coin, side, direction, px, size, closed_pnl_usd, fee_usd, raw_json
        FROM owned_wallet_fills
        WHERE wallet=:wallet
        ORDER BY ts_ms DESC
        LIMIT :limit
    ''', {'wallet': wallet, 'limit': limit})


def data_api_exposures(limit: int = 100) -> list[dict[str, Any]]:
    ensure_copycat_data_api()
    limit = max(1, min(int(limit or 100), 500))
    return fetch_all('''
        WITH latest_ts AS (SELECT max(ts_ms) AS ts_ms FROM positions), p AS (
          SELECT upper(coin) AS coin,
                 COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='long'),0) AS long_usd,
                 COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='short'),0) AS short_usd,
                 count(DISTINCT wallet) FILTER (WHERE lower(side)='long') AS wallets_long,
                 count(DISTINCT wallet) FILTER (WHERE lower(side)='short') AS wallets_short,
                 max(ts_ms) AS ts_ms
          FROM positions
          WHERE ts_ms=(SELECT ts_ms FROM latest_ts)
          GROUP BY upper(coin)
        )
        SELECT coin, ts_ms, long_usd, short_usd, long_usd-short_usd AS net_usd,
               wallets_long, wallets_short,
               CASE WHEN long_usd + short_usd > 0 THEN long_usd/(long_usd+short_usd) ELSE 0 END AS long_share,
               CASE WHEN long_usd + short_usd > 0 THEN short_usd/(long_usd+short_usd) ELSE 0 END AS short_share
        FROM p
        ORDER BY abs(long_usd-short_usd) DESC
        LIMIT :limit
    ''', {'limit': limit})


def data_api_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    ensure_copycat_data_api()
    limit = max(1, min(int(limit or 100), 500))
    return fetch_all('''
        SELECT event_id, wallet, event_type, ts_ms, coin, side, direction, px, size,
               notional_usd, closed_pnl_usd, fee_usd, source
        FROM copycat_live_events
        ORDER BY ts_ms DESC, id DESC
        LIMIT :limit
    ''', {'limit': limit})


def recent_live_orders(limit: int = 50) -> list[dict[str, Any]]:
    try:
        events = data_api_recent_events(limit)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for event in events:
        wallet = event.get('wallet') or ''
        event_type = str(event.get('event_type') or '').lower()
        direction = str(event.get('direction') or event.get('side') or '').strip()
        if event_type == 'fill':
            action = direction or 'Fill'
        elif event_type == 'order':
            action = f"Order {direction}".strip()
        else:
            action = direction or event_type.title()
        out.append({
            'ts_ms': event.get('ts_ms'),
            'wallet': wallet,
            'wallet_label': short_wallet(wallet) if wallet else 'Wallet',
            'coin': event.get('coin'),
            'side': action,
            'delta_value_usd': safe_float(event.get('notional_usd')),
            'position_value_usd': safe_float(event.get('notional_usd')),
            'previous_value_usd': 0,
            'source': 'live_ws',
        })
    return out


def historical_sources() -> list[dict[str, Any]]:
    ensure_copycat_data_api()
    return fetch_all('''
        SELECT name, source_type, url, legal_status, coverage, limitation, active, updated_at
        FROM copycat_historical_sources
        ORDER BY id ASC
    ''')

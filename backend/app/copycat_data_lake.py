from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from sqlalchemy import text

from .db import fetch_all, fetch_one, engine
from .settings import get_settings
from .worker import Hyperliquid, is_address, now_ms, safe_float
from .owned_data import ensure_owned_tables, _store_fills

log = logging.getLogger(__name__)



def short_wallet(wallet: str) -> str:
    wallet = str(wallet or '').strip()
    if len(wallet) <= 12:
        return wallet
    return f'{wallet[:6]}…{wallet[-4:]}'


def _coin_key(coin: str | None) -> str:
    raw = str(coin or '').strip()
    if ':' in raw:
        raw = raw.split(':', 1)[1]
    return raw.upper()


def _json(value: Any) -> str:
    return json.dumps(value, separators=(',', ':'), default=str)


_DATA_LAKE_TABLES_READY = False


def _lake_table_exists(conn, table_name: str) -> bool:
    try:
        return bool(conn.execute(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"}).scalar())
    except Exception:
        return False


def _lake_safe_ddl(conn, sql: str) -> None:
    try:
        conn.execute(text(sql))
    except Exception as exc:
        log.warning("data lake schema DDL skipped: %s", str(exc)[:220])


def ensure_copycat_data_lake_tables(conn) -> None:
    global _DATA_LAKE_TABLES_READY
    if _DATA_LAKE_TABLES_READY:
        return

    try:
        ensure_owned_tables(conn)
    except Exception as exc:
        log.warning('owned table ensure skipped from data lake: %s', str(exc)[:220])

    if (
        _lake_table_exists(conn, 'copycat_market_universe')
        and _lake_table_exists(conn, 'copycat_market_snapshots')
        and _lake_table_exists(conn, 'owned_wallet_backfill_state')
        and _lake_table_exists(conn, 'copycat_data_quality_snapshots')
    ):
        _DATA_LAKE_TABLES_READY = True
        return

    got_lock = False
    try:
        got_lock = bool(conn.execute(text('SELECT pg_try_advisory_lock(82420402)')).scalar())
    except Exception:
        got_lock = False
    if not got_lock:
        log.warning('data lake schema setup already in progress; skipping this pass')
        return

    try:
        _lake_safe_ddl(conn, '''
        CREATE TABLE IF NOT EXISTS copycat_market_universe (
          coin text PRIMARY KEY,
          display_name text NOT NULL,
          market_type text NOT NULL DEFAULT 'perp',
          sz_decimals integer,
          max_leverage integer,
          only_isolated boolean NOT NULL DEFAULT false,
          is_delisted boolean NOT NULL DEFAULT false,
          source text NOT NULL DEFAULT 'hyperliquid_meta',
          raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        ''')
        _lake_safe_ddl(conn, 'CREATE INDEX IF NOT EXISTS idx_copycat_market_universe_updated ON copycat_market_universe(updated_at DESC)')
        _lake_safe_ddl(conn, '''
        CREATE TABLE IF NOT EXISTS copycat_market_snapshots (
          id bigserial PRIMARY KEY,
          ts_ms bigint NOT NULL,
          coin text NOT NULL,
          mark_px double precision,
          oracle_px double precision,
          funding double precision,
          open_interest_contracts double precision,
          open_interest_usd double precision,
          day_ntl_vlm_usd double precision,
          prev_day_px double precision,
          source text NOT NULL DEFAULT 'hyperliquid_metaAndAssetCtxs',
          raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        ''')
        _lake_safe_ddl(conn, 'CREATE INDEX IF NOT EXISTS idx_copycat_market_snapshots_coin_ts ON copycat_market_snapshots(coin, ts_ms DESC)')
        _lake_safe_ddl(conn, 'CREATE INDEX IF NOT EXISTS idx_copycat_market_snapshots_ts ON copycat_market_snapshots(ts_ms DESC)')
        _lake_safe_ddl(conn, '''
        CREATE TABLE IF NOT EXISTS owned_wallet_backfill_state (
          wallet text PRIMARY KEY,
          earliest_fill_ts_ms bigint,
          latest_fill_ts_ms bigint,
          last_checked_ts_ms bigint,
          next_before_ts_ms bigint,
          fills_stored integer NOT NULL DEFAULT 0,
          pages_fetched integer NOT NULL DEFAULT 0,
          last_status text NOT NULL DEFAULT 'pending',
          last_error text NOT NULL DEFAULT '',
          coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        ''')
        _lake_safe_ddl(conn, 'CREATE INDEX IF NOT EXISTS idx_owned_wallet_backfill_status ON owned_wallet_backfill_state(last_status, updated_at)')
        _lake_safe_ddl(conn, '''
        CREATE TABLE IF NOT EXISTS copycat_data_quality_snapshots (
          id bigserial PRIMARY KEY,
          ts_ms bigint NOT NULL,
          status text NOT NULL,
          message text NOT NULL DEFAULT '',
          known_wallet_candidates integer NOT NULL DEFAULT 0,
          owned_wallets_indexed integer NOT NULL DEFAULT 0,
          owned_wallets_qualified integer NOT NULL DEFAULT 0,
          tracked_active_wallets integer NOT NULL DEFAULT 0,
          markets_monitored integer NOT NULL DEFAULT 0,
          stored_owned_fills integer NOT NULL DEFAULT 0,
          stored_live_events integer NOT NULL DEFAULT 0,
          backfilled_wallets integer NOT NULL DEFAULT 0,
          raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        ''')
        _lake_safe_ddl(conn, 'CREATE INDEX IF NOT EXISTS idx_copycat_data_quality_ts ON copycat_data_quality_snapshots(ts_ms DESC)')
        _DATA_LAKE_TABLES_READY = True
    finally:
        try:
            conn.execute(text('SELECT pg_advisory_unlock(82420402)'))
        except Exception:
            pass


def ensure_copycat_data_lake() -> None:
    with engine.begin() as conn:
        ensure_copycat_data_lake_tables(conn)


def _parse_meta_and_ctxs(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload, list) and len(payload) >= 2:
        meta = payload[0] if isinstance(payload[0], dict) else {}
        ctxs = payload[1] if isinstance(payload[1], list) else []
        universe = meta.get('universe') if isinstance(meta, dict) else []
        return [x for x in universe if isinstance(x, dict)], [x for x in ctxs if isinstance(x, dict)]
    if isinstance(payload, dict):
        universe = payload.get('universe') or payload.get('meta', {}).get('universe') or []
        ctxs = payload.get('assetCtxs') or payload.get('contexts') or []
        return [x for x in universe if isinstance(x, dict)], [x for x in ctxs if isinstance(x, dict)]
    return [], []


def refresh_market_universe_snapshot() -> dict[str, Any]:
    hl = Hyperliquid()
    ts = now_ms()
    payload = hl.info({'type': 'metaAndAssetCtxs'})
    universe, ctxs = _parse_meta_and_ctxs(payload)
    ctx_by_idx = {i: c for i, c in enumerate(ctxs)}
    inserted = 0
    with engine.begin() as conn:
        ensure_copycat_data_lake_tables(conn)
        for i, asset in enumerate(universe):
            name = _coin_key(asset.get('name') or asset.get('coin'))
            if not name:
                continue
            ctx = ctx_by_idx.get(i, {})
            mark_px = safe_float(ctx.get('markPx') or ctx.get('midPx'), None)
            open_interest = safe_float(ctx.get('openInterest'), None)
            open_interest_usd = abs(open_interest * mark_px) if open_interest is not None and mark_px is not None else None
            conn.execute(text('''
                INSERT INTO copycat_market_universe(
                  coin, display_name, market_type, sz_decimals, max_leverage, only_isolated,
                  is_delisted, source, raw_json, updated_at
                ) VALUES (
                  :coin, :display_name, 'perp', :sz_decimals, :max_leverage, :only_isolated,
                  :is_delisted, 'hyperliquid_meta', CAST(:raw_json AS jsonb), now()
                )
                ON CONFLICT(coin) DO UPDATE SET
                  display_name=excluded.display_name,
                  sz_decimals=excluded.sz_decimals,
                  max_leverage=excluded.max_leverage,
                  only_isolated=excluded.only_isolated,
                  is_delisted=excluded.is_delisted,
                  raw_json=excluded.raw_json,
                  updated_at=now()
            '''), {
                'coin': name,
                'display_name': name,
                'sz_decimals': asset.get('szDecimals'),
                'max_leverage': asset.get('maxLeverage'),
                'only_isolated': bool(asset.get('onlyIsolated') or False),
                'is_delisted': bool(asset.get('isDelisted') or False),
                'raw_json': _json({'asset': asset, 'ctx': ctx}),
            })
            conn.execute(text('''
                INSERT INTO copycat_market_snapshots(
                  ts_ms, coin, mark_px, oracle_px, funding, open_interest_contracts,
                  open_interest_usd, day_ntl_vlm_usd, prev_day_px, raw_json
                ) VALUES (
                  :ts_ms, :coin, :mark_px, :oracle_px, :funding, :open_interest_contracts,
                  :open_interest_usd, :day_ntl_vlm_usd, :prev_day_px, CAST(:raw_json AS jsonb)
                )
            '''), {
                'ts_ms': ts,
                'coin': name,
                'mark_px': mark_px,
                'oracle_px': safe_float(ctx.get('oraclePx'), None),
                'funding': safe_float(ctx.get('funding'), None),
                'open_interest_contracts': open_interest,
                'open_interest_usd': open_interest_usd,
                'day_ntl_vlm_usd': safe_float(ctx.get('dayNtlVlm'), None),
                'prev_day_px': safe_float(ctx.get('prevDayPx'), None),
                'raw_json': _json(ctx),
            })
            inserted += 1
    return {'status': 'ok', 'markets': inserted, 'ts_ms': ts}


def _leaderboard_query(where: str, params: dict[str, Any], limit: int, offset: int = 0) -> list[dict[str, Any]]:
    rows = fetch_all(f'''
        SELECT wallet, ts_ms, account_value_usd, total_ntl_pos_usd,
               pnl_day_usd, pnl_30d_usd, pnl_all_time_usd,
               closed_pnl_lookback_usd, fees_lookback_usd, fills_lookback_count,
               active_days_observed, score, qualifies, metrics_json
        FROM owned_wallet_metrics
        {where}
        ORDER BY qualifies DESC, score DESC, pnl_30d_usd DESC, account_value_usd DESC
        LIMIT :limit OFFSET :offset
    ''', {**params, 'limit': limit, 'offset': offset})
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1 + offset):
        metrics = row.get('metrics_json') or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        account = safe_float(row.get('account_value_usd'))
        pnl30 = safe_float(row.get('pnl_30d_usd'))
        pnlall = safe_float(row.get('pnl_all_time_usd'))
        out.append({
            'rank': i,
            'name': metrics.get('label') or metrics.get('name') or 'Copycat-ranked wallet',
            'wallet': row.get('wallet'),
            'wallet_label': short_wallet(row.get('wallet') or ''),
            'account_value_usd': round(account, 2),
            'open_position_value_usd': round(safe_float(row.get('total_ntl_pos_usd')), 2),
            'pnl_day_usd': round(safe_float(row.get('pnl_day_usd')), 2),
            'pnl_30d_usd': round(pnl30, 2),
            'pnl_all_time_usd': round(pnlall, 2),
            'roi_30d_pct': round((pnl30 / account) * 100, 4) if account > 0 else None,
            'roi_all_time_pct': round((pnlall / account) * 100, 4) if account > 0 else None,
            'score': round(safe_float(row.get('score')), 3),
            'qualifies': bool(row.get('qualifies')),
            'fills_lookback_count': int(row.get('fills_lookback_count') or 0),
            'active_days_observed': int(row.get('active_days_observed') or 0),
            'score_components': metrics.get('score_components') or {},
            'disqualifiers': metrics.get('disqualifiers') or [],
            'last_metric_ts_ms': row.get('ts_ms'),
            'source': 'hyperliquid_native',
        })
    return out


def leaderboard_v2(limit: int = 50, offset: int = 0, min_account_value_usd: float = 0, qualified_only: bool = True) -> dict[str, Any]:
    ensure_copycat_data_lake()
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    filters: list[str] = []
    params: dict[str, Any] = {}
    if qualified_only:
        filters.append('qualifies=true')
    if min_account_value_usd > 0:
        filters.append('account_value_usd >= :min_account')
        params['min_account'] = float(min_account_value_usd)
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    total = fetch_one(f'SELECT count(*) AS n FROM owned_wallet_metrics {where}', params) or {'n': 0}
    return {
        'status': 'ok',
        'source': 'hyperliquid_native',
        'algorithm': 'Copycat V2 profit-quality score',
        'coverage_note': 'Ranked from Copycat-indexed Hyperliquid wallets, not yet guaranteed all Hyperliquid wallets.',
        'total_matching_wallets': int(total.get('n') or 0),
        'limit': limit,
        'offset': offset,
        'data': _leaderboard_query(where, params, limit, offset),
    }


def leaderboard_preview(limit: int = 20) -> list[dict[str, Any]]:
    return leaderboard_v2(limit=limit, qualified_only=False).get('data', [])


def token_screener(limit: int = 100) -> dict[str, Any]:
    ensure_copycat_data_lake()
    limit = max(1, min(int(limit or 100), 500))
    rows = fetch_all('''
        WITH latest_market AS (
          SELECT DISTINCT ON (coin) coin, ts_ms, mark_px, oracle_px, funding,
                 open_interest_usd, day_ntl_vlm_usd, prev_day_px
          FROM copycat_market_snapshots
          ORDER BY coin, ts_ms DESC
        ), exposure AS (
          SELECT upper(coin) AS coin,
                 COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='long'),0) AS tracked_long_usd,
                 COALESCE(sum(position_value_usd) FILTER (WHERE lower(side)='short'),0) AS tracked_short_usd,
                 count(DISTINCT wallet) FILTER (WHERE lower(side)='long') AS tracked_wallets_long,
                 count(DISTINCT wallet) FILTER (WHERE lower(side)='short') AS tracked_wallets_short
          FROM copycat_live_positions
          GROUP BY upper(coin)
        )
        SELECT u.coin, u.display_name, COALESCE(m.ts_ms,0) AS market_ts_ms,
               m.mark_px, m.oracle_px, m.funding, m.open_interest_usd, m.day_ntl_vlm_usd,
               m.prev_day_px,
               COALESCE(e.tracked_long_usd,0) AS tracked_long_usd,
               COALESCE(e.tracked_short_usd,0) AS tracked_short_usd,
               COALESCE(e.tracked_wallets_long,0) AS tracked_wallets_long,
               COALESCE(e.tracked_wallets_short,0) AS tracked_wallets_short
        FROM copycat_market_universe u
        LEFT JOIN latest_market m ON m.coin=u.coin
        LEFT JOIN exposure e ON e.coin=u.coin
        WHERE COALESCE(u.is_delisted,false)=false
        ORDER BY COALESCE(m.day_ntl_vlm_usd,0) DESC, abs(COALESCE(e.tracked_long_usd,0)-COALESCE(e.tracked_short_usd,0)) DESC
        LIMIT :limit
    ''', {'limit': limit})
    out: list[dict[str, Any]] = []
    for row in rows:
        price = safe_float(row.get('mark_px'))
        prev = safe_float(row.get('prev_day_px'))
        long_usd = safe_float(row.get('tracked_long_usd'))
        short_usd = safe_float(row.get('tracked_short_usd'))
        out.append({
            'coin': row.get('coin'),
            'display_name': row.get('display_name') or row.get('coin'),
            'price_usd': price if price > 0 else None,
            'change_24h_pct': round(((price - prev) / prev) * 100, 4) if price > 0 and prev > 0 else None,
            'volume_24h_usd': round(safe_float(row.get('day_ntl_vlm_usd')), 2),
            'open_interest_usd': round(safe_float(row.get('open_interest_usd')), 2),
            'funding': safe_float(row.get('funding'), None),
            'tracked_long_usd': round(long_usd, 2),
            'tracked_short_usd': round(short_usd, 2),
            'tracked_net_usd': round(long_usd - short_usd, 2),
            'tracked_wallets_long': int(row.get('tracked_wallets_long') or 0),
            'tracked_wallets_short': int(row.get('tracked_wallets_short') or 0),
            'market_ts_ms': row.get('market_ts_ms'),
        })
    return {'status': 'ok', 'source': 'hyperliquid_native', 'data': out}


def token_screener_preview(limit: int = 20) -> list[dict[str, Any]]:
    return token_screener(limit=limit).get('data', [])


def historical_fill_backfill_wallet(wallet: str, days: int | None = None, max_pages: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    wallet = (wallet or '').lower().strip()
    if not is_address(wallet):
        return {'wallet': wallet, 'status': 'error', 'error': 'invalid wallet'}
    days = int(days or getattr(settings, 'owned_backfill_days', 365))
    max_pages = int(max_pages or getattr(settings, 'owned_backfill_max_pages_per_wallet', 5))
    start = now_ms() - max(1, days) * 86_400_000
    end = now_ms()
    hl = Hyperliquid()
    with engine.begin() as conn:
        locked = bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext('copycat_backfill:' || :wallet))"), {'wallet': wallet}).scalar())
    if not locked:
        return {'wallet': wallet, 'status': 'skipped', 'error': 'wallet backfill already running'}
    pages = 0
    stored = 0
    earliest = None
    latest = None
    last_error = ''
    with engine.begin() as conn:
        ensure_copycat_data_lake_tables(conn)
    for _ in range(max(1, max_pages)):
        pages += 1
        try:
            fills_raw = hl.user_fills_by_time(wallet, start, end, aggregate_by_time=True)
            fills = [f for f in fills_raw if isinstance(f, dict)] if isinstance(fills_raw, list) else []
        except Exception as exc:
            last_error = str(exc)[:300]
            break
        if not fills:
            break
        with engine.begin() as conn:
            summary = _store_fills(conn, wallet, fills)
            stored += int(summary.get('fills_lookback_count') or 0)
        times = [int(safe_float(f.get('time') or f.get('timestamp'), 0)) for f in fills]
        times = [t for t in times if t > 0]
        if times:
            earliest = min([earliest] + times) if earliest else min(times)
            latest = max([latest] + times) if latest else max(times)
            end = max(start, min(times) - 1)
        if len(fills) < 2000 or end <= start:
            break
        time.sleep(0.2)
    status = 'ok' if not last_error else 'partial'
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO owned_wallet_backfill_state(
              wallet, earliest_fill_ts_ms, latest_fill_ts_ms, last_checked_ts_ms,
              next_before_ts_ms, fills_stored, pages_fetched, last_status, last_error,
              coverage_json, updated_at
            ) VALUES (
              :wallet, :earliest, :latest, :checked, :next_before, :stored, :pages,
              :status, :error, CAST(:coverage_json AS jsonb), now()
            )
            ON CONFLICT(wallet) DO UPDATE SET
              earliest_fill_ts_ms=LEAST(COALESCE(owned_wallet_backfill_state.earliest_fill_ts_ms, excluded.earliest_fill_ts_ms), COALESCE(excluded.earliest_fill_ts_ms, owned_wallet_backfill_state.earliest_fill_ts_ms)),
              latest_fill_ts_ms=GREATEST(COALESCE(owned_wallet_backfill_state.latest_fill_ts_ms, excluded.latest_fill_ts_ms), COALESCE(excluded.latest_fill_ts_ms, owned_wallet_backfill_state.latest_fill_ts_ms)),
              last_checked_ts_ms=excluded.last_checked_ts_ms,
              next_before_ts_ms=excluded.next_before_ts_ms,
              fills_stored=owned_wallet_backfill_state.fills_stored + excluded.fills_stored,
              pages_fetched=owned_wallet_backfill_state.pages_fetched + excluded.pages_fetched,
              last_status=excluded.last_status,
              last_error=excluded.last_error,
              coverage_json=excluded.coverage_json,
              updated_at=now()
        '''), {
            'wallet': wallet,
            'earliest': earliest,
            'latest': latest,
            'checked': now_ms(),
            'next_before': end,
            'stored': stored,
            'pages': pages,
            'status': status,
            'error': last_error,
            'coverage_json': _json({'requested_days': days, 'max_pages': max_pages, 'official_limit_note': 'Hyperliquid userFillsByTime exposes up to 2000 fills per response and only the 10000 most recent fills per user.'}),
        })
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext('copycat_backfill:' || :wallet))"), {'wallet': wallet})
    except Exception:
        pass
    return {'wallet': wallet, 'status': status, 'fills_seen': stored, 'pages': pages, 'earliest_fill_ts_ms': earliest, 'latest_fill_ts_ms': latest, 'error': last_error}


def run_historical_fill_backfill(limit: int | None = None, max_seconds: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    limit = int(limit or getattr(settings, 'owned_backfill_wallet_limit', 25))
    max_seconds = int(max_seconds or getattr(settings, 'owned_backfill_max_seconds', 900))
    started = time.time()
    with engine.begin() as conn:
        ensure_copycat_data_lake_tables(conn)
        rows = conn.execute(text('''
            SELECT w.wallet FROM (
              SELECT wallet, 0 AS priority, score AS scoreish FROM qualified_wallets WHERE status='active'
              UNION ALL
              SELECT wallet, 1 AS priority, score AS scoreish FROM owned_wallet_metrics
              UNION ALL
              SELECT wallet, 2 AS priority, 0 AS scoreish FROM wallet_candidates WHERE active=true
            ) w
            LEFT JOIN owned_wallet_backfill_state b ON lower(b.wallet)=lower(w.wallet)
            WHERE w.wallet ~* '^0x[0-9a-f]{40}$'
            GROUP BY w.wallet
            ORDER BY COALESCE(min(b.updated_at), '1970-01-01'::timestamptz) ASC,
                     min(priority), max(scoreish) DESC NULLS LAST
            LIMIT :limit
        '''), {'limit': limit}).fetchall()
    ok = 0
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        if max_seconds > 0 and time.time() - started >= max_seconds:
            break
        wallet = row[0]
        log.info('Historical fill backfill %s/%s %s', i, len(rows), wallet)
        result = historical_fill_backfill_wallet(wallet)
        results.append(result)
        if result.get('status') == 'ok':
            ok += 1
        else:
            errors.append(f"{wallet}: {result.get('error')}")
        time.sleep(0.25)
    return {'status': 'ok' if not errors else 'partial', 'wallets_requested': len(rows), 'wallets_ok': ok, 'errors': errors[:10], 'elapsed_seconds': round(time.time() - started, 1), 'sample': results[:3]}


def backfill_coverage() -> dict[str, Any]:
    ensure_copycat_data_lake()
    row = fetch_one('''
        SELECT count(*) AS wallets,
               count(*) FILTER (WHERE last_status='ok') AS ok_wallets,
               sum(fills_stored) AS fills_stored,
               min(earliest_fill_ts_ms) AS earliest_fill_ts_ms,
               max(latest_fill_ts_ms) AS latest_fill_ts_ms,
               max(updated_at) AS latest_backfill_at
        FROM owned_wallet_backfill_state
    ''') or {}
    return {
        'status': 'ok',
        'wallets_backfilled': int(row.get('wallets') or 0),
        'wallets_ok': int(row.get('ok_wallets') or 0),
        'fills_stored_by_backfill_worker': int(row.get('fills_stored') or 0),
        'earliest_fill_ts_ms': row.get('earliest_fill_ts_ms'),
        'latest_fill_ts_ms': row.get('latest_fill_ts_ms'),
        'latest_backfill_at': str(row.get('latest_backfill_at')) if row.get('latest_backfill_at') else None,
        'official_limit_note': 'Hyperliquid userFillsByTime provides recent per-wallet fills; Copycat stores everything it observes from now on, but older complete all-wallet history needs an external/full archive feed.',
    }


def historical_fills(wallet: str | None = None, coin: str | None = None, limit: int = 500, before_ts_ms: int | None = None) -> list[dict[str, Any]]:
    ensure_copycat_data_lake()
    limit = max(1, min(int(limit or 500), 5000))
    filters = []
    params: dict[str, Any] = {'limit': limit}
    if wallet:
        filters.append('wallet=:wallet')
        params['wallet'] = wallet.lower().strip()
    if coin:
        filters.append('upper(coin)=:coin')
        params['coin'] = _coin_key(coin)
    if before_ts_ms:
        filters.append('ts_ms < :before_ts_ms')
        params['before_ts_ms'] = int(before_ts_ms)
    where = ('WHERE ' + ' AND '.join(filters)) if filters else ''
    return fetch_all(f'''
        SELECT wallet, tid, ts_ms, coin, side, direction, px, size, closed_pnl_usd, fee_usd
        FROM owned_wallet_fills
        {where}
        ORDER BY ts_ms DESC
        LIMIT :limit
    ''', params)


def wallet_universe(limit: int = 500, offset: int = 0) -> dict[str, Any]:
    ensure_copycat_data_lake()
    limit = max(1, min(int(limit or 500), 5000))
    offset = max(0, int(offset or 0))
    rows = fetch_all('''
        SELECT COALESCE(m.wallet, c.wallet) AS wallet,
               m.account_value_usd, m.pnl_30d_usd, m.pnl_all_time_usd, m.score, m.qualifies,
               c.source AS candidate_source,
               b.last_status AS backfill_status,
               b.fills_stored AS backfilled_fills,
               b.earliest_fill_ts_ms, b.latest_fill_ts_ms
        FROM wallet_candidates c
        FULL OUTER JOIN owned_wallet_metrics m ON lower(m.wallet)=lower(c.wallet)
        LEFT JOIN owned_wallet_backfill_state b ON lower(b.wallet)=lower(COALESCE(m.wallet, c.wallet))
        WHERE COALESCE(m.wallet, c.wallet) ~* '^0x[0-9a-f]{40}$'
        ORDER BY COALESCE(m.qualifies,false) DESC, COALESCE(m.score,0) DESC, COALESCE(m.account_value_usd,0) DESC
        LIMIT :limit OFFSET :offset
    ''', {'limit': limit, 'offset': offset})
    total = fetch_one('''
        SELECT count(DISTINCT wallet) AS n FROM (
          SELECT wallet FROM wallet_candidates WHERE wallet ~* '^0x[0-9a-f]{40}$'
          UNION SELECT wallet FROM owned_wallet_metrics WHERE wallet ~* '^0x[0-9a-f]{40}$'
        ) w
    ''') or {'n': 0}
    for row in rows:
        row['wallet_label'] = short_wallet(row.get('wallet') or '')
    return {'status': 'ok', 'known_wallets': int(total.get('n') or 0), 'limit': limit, 'offset': offset, 'data': rows}


def quality_snapshot() -> dict[str, Any]:
    ensure_copycat_data_lake()
    known = fetch_one('''
        SELECT count(DISTINCT wallet) AS n FROM (
          SELECT wallet FROM wallet_candidates WHERE wallet ~* '^0x[0-9a-f]{40}$'
          UNION SELECT wallet FROM owned_wallet_metrics WHERE wallet ~* '^0x[0-9a-f]{40}$'
        ) w
    ''') or {'n': 0}
    owned = fetch_one('SELECT count(*) AS n, count(*) FILTER (WHERE qualifies=true) AS q, max(ts_ms) AS latest FROM owned_wallet_metrics') or {}
    active = fetch_one("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'") or {'n': 0}
    markets = fetch_one('SELECT count(*) AS n, max(updated_at) AS latest FROM copycat_market_universe WHERE is_delisted=false') or {}
    fills = fetch_one('SELECT count(*) AS n, max(ts_ms) AS latest FROM owned_wallet_fills') or {}
    events = fetch_one('SELECT count(*) AS n, max(ts_ms) AS latest FROM copycat_live_events') or {}
    backfill = fetch_one('SELECT count(*) AS n FROM owned_wallet_backfill_state') or {}
    min_indexed = int(os.getenv('OWNED_TOP_CLAIM_MIN_INDEXED_WALLETS', '10000') or '10000')
    status = 'healthy' if int(active.get('n') or 0) == 50 and int(markets.get('n') or 0) > 0 else 'warning'
    result = {
        'status': status,
        'source': 'hyperliquid_native',
        'external_paid_data_required': False,
        'known_wallet_candidates': int(known.get('n') or 0),
        'owned_wallets_indexed': int(owned.get('n') or 0),
        'owned_wallets_qualified': int(owned.get('q') or 0),
        'tracked_active_wallets': int(active.get('n') or 0),
        'markets_monitored': int(markets.get('n') or 0),
        'stored_owned_fills': int(fills.get('n') or 0),
        'stored_live_events': int(events.get('n') or 0),
        'backfilled_wallets': int(backfill.get('n') or 0),
        'top_claim_ready': int(owned.get('n') or 0) >= min_indexed,
        'top_claim_min_indexed_wallets': min_indexed,
        'latest_metric_ts_ms': owned.get('latest'),
        'latest_fill_ts_ms': fills.get('latest'),
        'latest_live_event_ts_ms': events.get('latest'),
        'limitations': [
            'Official Hyperliquid user fill API is recent-window limited per wallet.',
            'Copycat stores all data it observes from now on.',
            'A complete all-platform historical top-50 claim requires a full historical wallet universe feed or long-running collection coverage.',
        ],
    }
    with engine.begin() as conn:
        conn.execute(text('''
            INSERT INTO copycat_data_quality_snapshots(
              ts_ms,status,message,known_wallet_candidates,owned_wallets_indexed,
              owned_wallets_qualified,tracked_active_wallets,markets_monitored,
              stored_owned_fills,stored_live_events,backfilled_wallets,raw_json
            ) VALUES (
              :ts_ms,:status,:message,:known_wallet_candidates,:owned_wallets_indexed,
              :owned_wallets_qualified,:tracked_active_wallets,:markets_monitored,
              :stored_owned_fills,:stored_live_events,:backfilled_wallets,CAST(:raw_json AS jsonb)
            )
        '''), {
            'ts_ms': now_ms(),
            'status': status,
            'message': 'Copycat native data lake status',
            **{k: result[k] for k in ('known_wallet_candidates','owned_wallets_indexed','owned_wallets_qualified','tracked_active_wallets','markets_monitored','stored_owned_fills','stored_live_events','backfilled_wallets')},
            'raw_json': _json(result),
        })
    return result

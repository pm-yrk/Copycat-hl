from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from .db import engine
from .settings import get_settings
from .worker import (
    Hyperliquid,
    clamp,
    collect_once,
    extract_margin_summary,
    insert_run,
    is_address,
    now_ms,
    portfolio_pnl,
    safe_float,
    wallet_score,
)

log = logging.getLogger(__name__)

_ADDRESS_RE = re.compile(r'0x[a-fA-F0-9]{40}')


def _lookback_start_ms(days: int) -> int:
    return now_ms() - max(1, int(days)) * 86_400_000


def _parse_seed_wallets(raw: str | None) -> list[str]:
    if not raw:
        return []
    found = _ADDRESS_RE.findall(raw)
    return sorted({w.lower() for w in found if is_address(w)})


def ensure_owned_tables(conn) -> None:
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS owned_wallet_fills (
          id bigserial PRIMARY KEY,
          wallet text NOT NULL,
          tid text NOT NULL,
          ts_ms bigint NOT NULL,
          ts timestamptz NOT NULL DEFAULT now(),
          coin text,
          side text,
          direction text,
          px double precision,
          size double precision,
          closed_pnl_usd double precision,
          fee_usd double precision,
          raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE(wallet, tid)
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_fills_wallet_ts ON owned_wallet_fills(wallet, ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_fills_ts ON owned_wallet_fills(ts_ms DESC)'))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS owned_wallet_metrics (
          wallet text PRIMARY KEY,
          ts_ms bigint NOT NULL,
          ts timestamptz NOT NULL DEFAULT now(),
          source text NOT NULL DEFAULT 'hyperliquid_native',
          account_value_usd double precision NOT NULL DEFAULT 0,
          total_ntl_pos_usd double precision NOT NULL DEFAULT 0,
          pnl_day_usd double precision NOT NULL DEFAULT 0,
          pnl_30d_usd double precision NOT NULL DEFAULT 0,
          pnl_all_time_usd double precision NOT NULL DEFAULT 0,
          closed_pnl_lookback_usd double precision NOT NULL DEFAULT 0,
          fees_lookback_usd double precision NOT NULL DEFAULT 0,
          fills_lookback_count integer NOT NULL DEFAULT 0,
          active_days_observed integer NOT NULL DEFAULT 0,
          score double precision NOT NULL DEFAULT 0,
          qualifies boolean NOT NULL DEFAULT false,
          metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_metrics_score ON owned_wallet_metrics(qualifies, score DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_metrics_ts ON owned_wallet_metrics(ts_ms DESC)'))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS owned_wallet_metric_history (
          id bigserial PRIMARY KEY,
          wallet text NOT NULL,
          ts_ms bigint NOT NULL,
          ts timestamptz NOT NULL DEFAULT now(),
          source text NOT NULL DEFAULT 'hyperliquid_native',
          account_value_usd double precision NOT NULL DEFAULT 0,
          total_ntl_pos_usd double precision NOT NULL DEFAULT 0,
          pnl_day_usd double precision NOT NULL DEFAULT 0,
          pnl_30d_usd double precision NOT NULL DEFAULT 0,
          pnl_all_time_usd double precision NOT NULL DEFAULT 0,
          closed_pnl_lookback_usd double precision NOT NULL DEFAULT 0,
          fees_lookback_usd double precision NOT NULL DEFAULT 0,
          fills_lookback_count integer NOT NULL DEFAULT 0,
          active_days_observed integer NOT NULL DEFAULT 0,
          score double precision NOT NULL DEFAULT 0,
          qualifies boolean NOT NULL DEFAULT false,
          metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    '''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_wallet_ts ON owned_wallet_metric_history(wallet, ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_ts ON owned_wallet_metric_history(ts_ms DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS idx_owned_wallet_metric_history_score ON owned_wallet_metric_history(ts_ms DESC, qualifies, score DESC)'))
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS owned_wallet_scan_state (
          key text PRIMARY KEY,
          last_started_at timestamptz,
          last_finished_at timestamptz,
          last_status text,
          metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    '''))


def seed_owned_candidates() -> int:
    """Seed the independent engine without calling Nansen.

    We keep any existing wallet_candidates as the initial universe. This lets the
    product stop depending on Nansen from today while the native engine builds
    its own ongoing metrics. New fresh wallets can be added through the
    OWNED_DISCOVERY_SEED_WALLETS env var or future Hyperliquid explorer scans.
    """
    settings = get_settings()
    env_wallets = _parse_seed_wallets(settings.owned_discovery_seed_wallets or os.getenv('OWNED_DISCOVERY_SEED_WALLETS', ''))
    with engine.begin() as conn:
        ensure_owned_tables(conn)
        inserted = 0
        for wallet in env_wallets:
            conn.execute(text('''
                INSERT INTO wallet_candidates(wallet,label,source,notes,active)
                VALUES(:wallet,'','hyperliquid_native_seed','manual/native seed',true)
                ON CONFLICT(wallet) DO UPDATE SET active=true, source=CASE WHEN wallet_candidates.source IS NULL OR wallet_candidates.source='' THEN excluded.source ELSE wallet_candidates.source END
            '''), {'wallet': wallet})
            inserted += 1

        # If a wallet is already active or previously discovered, keep it in the
        # native universe. This does not call Nansen and does not require credits.
        existing = conn.execute(text('''
            SELECT count(*) AS n
            FROM wallet_candidates
            WHERE active=true AND wallet ~* '^0x[0-9a-f]{40}$'
        ''')).scalar() or 0
        active = conn.execute(text("SELECT count(*) AS n FROM qualified_wallets WHERE status='active'")).scalar() or 0
        insert_run(conn, 'owned_seed_candidates', 'ok', f'existing_candidates={existing}; active_wallets={active}; env_seeded={inserted}')
    return int(existing) + int(active)


def _normalise_fill(wallet: str, fill: dict[str, Any]) -> dict[str, Any] | None:
    tid = fill.get('tid') or fill.get('hash') or fill.get('oid')
    ts = int(safe_float(fill.get('time') or fill.get('timestamp'), 0))
    if not tid or ts <= 0:
        return None
    fee = abs(safe_float(fill.get('fee'), 0.0))
    return {
        'wallet': wallet,
        'tid': str(tid),
        'ts_ms': ts,
        'coin': fill.get('coin'),
        'side': fill.get('side'),
        'direction': fill.get('dir'),
        'px': safe_float(fill.get('px'), None),
        'size': safe_float(fill.get('sz') or fill.get('size'), None),
        'closed_pnl_usd': safe_float(fill.get('closedPnl') or fill.get('closed_pnl'), 0.0),
        'fee_usd': fee,
        'raw_json': json.dumps(fill),
    }


def _store_fills(conn, wallet: str, fills: list[dict[str, Any]]) -> dict[str, Any]:
    count = 0
    closed = 0.0
    fees = 0.0
    active_days: set[str] = set()
    for fill in fills:
        row = _normalise_fill(wallet, fill)
        if not row:
            continue
        count += 1
        closed += safe_float(row['closed_pnl_usd'])
        fees += abs(safe_float(row['fee_usd']))
        try:
            active_days.add(datetime.fromtimestamp(row['ts_ms'] / 1000, timezone.utc).date().isoformat())
        except Exception:
            pass
        conn.execute(text('''
            INSERT INTO owned_wallet_fills(wallet,tid,ts_ms,coin,side,direction,px,size,closed_pnl_usd,fee_usd,raw_json)
            VALUES(:wallet,:tid,:ts_ms,:coin,:side,:direction,:px,:size,:closed_pnl_usd,:fee_usd,CAST(:raw_json AS jsonb))
            ON CONFLICT(wallet, tid) DO UPDATE SET
              ts_ms=excluded.ts_ms,
              coin=excluded.coin,
              side=excluded.side,
              direction=excluded.direction,
              px=excluded.px,
              size=excluded.size,
              closed_pnl_usd=excluded.closed_pnl_usd,
              fee_usd=excluded.fee_usd,
              raw_json=excluded.raw_json
        '''), row)
    return {
        'fills_lookback_count': count,
        'closed_pnl_lookback_usd': closed,
        'fees_lookback_usd': fees,
        'active_days_observed': len(active_days),
        'net_closed_pnl_lookback_usd': closed - fees,
    }


def _owned_qualifies(score_row: dict[str, Any], fill_summary: dict[str, Any]) -> bool:
    settings = get_settings()
    account = safe_float(score_row.get('account_value_usd'))
    pnl30 = safe_float(score_row.get('pnl_30d_usd'))
    if pnl30 == 0 and fill_summary.get('fills_lookback_count', 0) > 0:
        pnl30 = safe_float(fill_summary.get('net_closed_pnl_lookback_usd'))
    fill_requirement_ok = (
        True
        if not settings.owned_discovery_fetch_fills
        else int(fill_summary.get('fills_lookback_count') or 0) >= settings.owned_discovery_min_fills_lookback
    )
    return (
        account >= settings.owned_discovery_min_account_value_usd
        and pnl30 >= settings.owned_discovery_min_30d_pnl_usd
        and safe_float(score_row.get('pnl_all_time_usd')) >= settings.owned_discovery_min_all_time_pnl_usd
        and safe_float(score_row.get('score')) >= settings.owned_discovery_min_score
        and fill_requirement_ok
    )


def refresh_owned_wallet(wallet: str, lookback_days: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    lookback_days = int(lookback_days or settings.owned_discovery_lookback_days)
    hl = Hyperliquid()
    state = hl.clearinghouse_state(wallet)
    portfolio = hl.portfolio(wallet)
    fills: list[dict[str, Any]] = []
    if settings.owned_discovery_fetch_fills:
        try:
            fills_raw = hl.user_fills_by_time(wallet, _lookback_start_ms(lookback_days), now_ms(), aggregate_by_time=True)
            if isinstance(fills_raw, list):
                fills = [f for f in fills_raw if isinstance(f, dict)]
        except Exception as exc:
            log.warning('owned fills failed for %s: %s', wallet, exc)

    score_row = wallet_score(wallet, state, portfolio)
    summary = extract_margin_summary(state)
    pnl = portfolio_pnl(portfolio)

    with engine.begin() as conn:
        ensure_owned_tables(conn)
        fill_summary = _store_fills(conn, wallet, fills)
        native_pnl30 = safe_float(score_row.get('pnl_30d_usd'))
        fill_net = safe_float(fill_summary.get('net_closed_pnl_lookback_usd'))
        # Use the stronger real PnL signal when portfolio month data is empty.
        pnl30 = native_pnl30 if native_pnl30 != 0 else fill_net
        score_row['pnl_30d_usd'] = pnl30
        qualifies = _owned_qualifies(score_row, fill_summary)
        metrics = {
            **json.loads(score_row.get('metrics_json') or '{}'),
            'source': 'hyperliquid_native',
            'lookback_days': lookback_days,
            'fill_summary': fill_summary,
            'pnl_source': 'portfolio' if native_pnl30 != 0 else 'userFillsByTime',
            'nansen_dependency': False,
        }
        metric_row = {
            'wallet': wallet,
            'ts_ms': now_ms(),
            'account_value_usd': summary.get('account_value_usd') or 0,
            'total_ntl_pos_usd': summary.get('total_ntl_pos_usd') or 0,
            'pnl_day_usd': pnl.get('pnl_day_usd') or 0,
            'pnl_30d_usd': pnl30,
            'pnl_all_time_usd': score_row.get('pnl_all_time_usd') or 0,
            'closed_pnl_lookback_usd': fill_summary.get('closed_pnl_lookback_usd') or 0,
            'fees_lookback_usd': fill_summary.get('fees_lookback_usd') or 0,
            'fills_lookback_count': fill_summary.get('fills_lookback_count') or 0,
            'active_days_observed': fill_summary.get('active_days_observed') or int(pnl.get('active_days_observed') or 0),
            'score': score_row.get('score') or 0,
            'qualifies': qualifies,
            'metrics_json': json.dumps(metrics),
        }
        conn.execute(text('''
            INSERT INTO owned_wallet_metrics(
              wallet, ts_ms, source, account_value_usd, total_ntl_pos_usd,
              pnl_day_usd, pnl_30d_usd, pnl_all_time_usd,
              closed_pnl_lookback_usd, fees_lookback_usd, fills_lookback_count,
              active_days_observed, score, qualifies, metrics_json
            ) VALUES (
              :wallet, :ts_ms, 'hyperliquid_native', :account_value_usd, :total_ntl_pos_usd,
              :pnl_day_usd, :pnl_30d_usd, :pnl_all_time_usd,
              :closed_pnl_lookback_usd, :fees_lookback_usd, :fills_lookback_count,
              :active_days_observed, :score, :qualifies, CAST(:metrics_json AS jsonb)
            )
            ON CONFLICT(wallet) DO UPDATE SET
              ts_ms=excluded.ts_ms,
              ts=now(),
              source=excluded.source,
              account_value_usd=excluded.account_value_usd,
              total_ntl_pos_usd=excluded.total_ntl_pos_usd,
              pnl_day_usd=excluded.pnl_day_usd,
              pnl_30d_usd=excluded.pnl_30d_usd,
              pnl_all_time_usd=excluded.pnl_all_time_usd,
              closed_pnl_lookback_usd=excluded.closed_pnl_lookback_usd,
              fees_lookback_usd=excluded.fees_lookback_usd,
              fills_lookback_count=excluded.fills_lookback_count,
              active_days_observed=excluded.active_days_observed,
              score=excluded.score,
              qualifies=excluded.qualifies,
              metrics_json=excluded.metrics_json
        '''), metric_row)
        conn.execute(text('''
            INSERT INTO owned_wallet_metric_history(
              wallet, ts_ms, source, account_value_usd, total_ntl_pos_usd,
              pnl_day_usd, pnl_30d_usd, pnl_all_time_usd,
              closed_pnl_lookback_usd, fees_lookback_usd, fills_lookback_count,
              active_days_observed, score, qualifies, metrics_json
            ) VALUES (
              :wallet, :ts_ms, 'hyperliquid_native', :account_value_usd, :total_ntl_pos_usd,
              :pnl_day_usd, :pnl_30d_usd, :pnl_all_time_usd,
              :closed_pnl_lookback_usd, :fees_lookback_usd, :fills_lookback_count,
              :active_days_observed, :score, :qualifies, CAST(:metrics_json AS jsonb)
            )
        '''), metric_row)
    return {'wallet': wallet, 'score': score_row.get('score'), 'qualifies': qualifies, **fill_summary}



def owned_universe_stats() -> dict[str, Any]:
    """Return truth-in-labeling stats for the owned Hyperliquid wallet universe."""
    settings = get_settings()
    min_claim = int(settings.owned_top_claim_min_indexed_wallets or 10000)
    with engine.begin() as conn:
        # Read-only and intentionally no schema migration here. This function is
        # called by hot dashboard endpoints, so it must never take DDL locks.
        try:
            candidates = conn.execute(text('''
                SELECT count(DISTINCT lower(wallet))
                FROM wallet_candidates
                WHERE active=true AND wallet ~* '^0x[0-9a-f]{40}$'
            ''')).scalar() or 0
        except Exception:
            candidates = 0
        try:
            active = conn.execute(text("SELECT count(*) FROM qualified_wallets WHERE status='active'")).scalar() or 0
        except Exception:
            active = 0
        try:
            metrics = conn.execute(text('''
                SELECT count(*) AS indexed,
                       count(*) FILTER (WHERE qualifies=true) AS qualified,
                       max(ts_ms) AS latest_metric_ts_ms
                FROM owned_wallet_metrics
            ''')).mappings().first() or {}
        except Exception:
            metrics = {'indexed': 0, 'qualified': 0, 'latest_metric_ts_ms': None}
        try:
            recent_scanner = conn.execute(text('''
                SELECT ts_ms, status, message
                FROM collector_runs
                WHERE run_type IN ('owned_wallet_scanner','owned_wallet_scanner_batch','owned_wallet_metrics','owned_wallet_refresh')
                ORDER BY ts_ms DESC
                LIMIT 1
            ''')).mappings().first() or {}
        except Exception:
            recent_scanner = {}
    indexed = int(metrics.get('indexed') or 0)
    qualified = int(metrics.get('qualified') or 0)
    universe_count = max(int(candidates or 0), indexed)
    top_claim_ready = indexed >= min_claim
    scope = f"Top {int(active or 0)} Copycat-ranked wallets from {indexed:,} indexed / {universe_count:,} known Hyperliquid wallets"
    guarded_claim = 'Top 50 most profitable wallets on Hyperliquid' if top_claim_ready else scope
    return {
        'source': 'hyperliquid_native',
        'nansen_required': False,
        'known_wallet_candidates': universe_count,
        'owned_wallets_indexed': indexed,
        'owned_wallets_qualified': qualified,
        'active_copycat_ranked_wallets': int(active or 0),
        'top_claim_min_indexed_wallets': min_claim,
        'top_claim_ready': bool(top_claim_ready),
        'ranking_scope_label': scope,
        'guarded_claim_label': guarded_claim,
        'latest_metric_ts_ms': metrics.get('latest_metric_ts_ms'),
        'latest_scanner_run': dict(recent_scanner or {}),
    }


def _refresh_owned_wallet_list(wallets: list[str], max_seconds: int, run_type: str = 'owned_wallet_metrics') -> dict[str, Any]:
    settings = get_settings()
    ok = 0
    errors: list[str] = []
    stopped_due_to_time = False
    started = time.time()
    clean_wallets: list[str] = []
    seen: set[str] = set()
    for w in wallets:
        wallet = str(w or '').lower()
        if is_address(wallet) and wallet not in seen:
            clean_wallets.append(wallet)
            seen.add(wallet)
    for i, wallet in enumerate(clean_wallets, start=1):
        elapsed = time.time() - started
        if max_seconds > 0 and elapsed >= max_seconds:
            stopped_due_to_time = True
            log.warning('%s stopped at %s/%s after %.1fs max_seconds=%s', run_type, i - 1, len(clean_wallets), elapsed, max_seconds)
            break
        log.info('%s %s/%s start %s', run_type, i, len(clean_wallets), wallet)
        wallet_started = time.time()
        try:
            refresh_owned_wallet(wallet)
            ok += 1
            log.info('%s %s/%s done %s %.1fs', run_type, i, len(clean_wallets), wallet, time.time() - wallet_started)
        except Exception as exc:
            log.exception('%s failed %s', run_type, wallet)
            errors.append(f'{wallet}: {str(exc)[:160]}')
        time.sleep(max(0.0, float(settings.owned_discovery_request_delay_seconds)))
    status = 'ok' if not errors and not stopped_due_to_time else 'partial'
    elapsed_total = round(time.time() - started, 1)
    with engine.begin() as conn:
        insert_run(conn, run_type, status, f'ok={ok}; errors={len(errors)}; stopped_due_to_time={stopped_due_to_time}; elapsed={elapsed_total:.1f}s')
    return {
        'wallets_requested': len(clean_wallets),
        'wallets_checked': ok + len(errors),
        'wallets_ok': ok,
        'errors': errors[:10],
        'stopped_due_to_time': stopped_due_to_time,
        'elapsed_seconds': elapsed_total,
    }


def refresh_owned_scanner_batch(limit: int | None = None, max_seconds: int | None = None) -> dict[str, Any]:
    """Deep scanner for the owned universe.

    This is intentionally separate from the daily refresh. It scans the known
    candidate universe in least-recently-indexed order and slowly builds the
    ranking database without blocking the live product.
    """
    settings = get_settings()
    limit = int(limit or settings.owned_scanner_batch_size)
    max_seconds = int(max_seconds or settings.owned_scanner_max_seconds)
    lock_conn = engine.connect()
    try:
        got_lock = bool(lock_conn.execute(text('SELECT pg_try_advisory_lock(5525012027)')).scalar())
        if not got_lock:
            with engine.begin() as conn:
                insert_run(conn, 'owned_wallet_scanner', 'skipped', 'another owned scanner batch is already running')
            return {'status': 'skipped', 'source': 'hyperliquid_native', 'nansen_used': False, 'message': 'another owned scanner batch is already running'}
        seeded = seed_owned_candidates()
        with engine.begin() as conn:
            ensure_owned_tables(conn)
            conn.execute(text('''
                INSERT INTO owned_wallet_scan_state(key,last_started_at,last_status,metadata_json)
                VALUES('main', now(), 'running', jsonb_build_object('limit', :limit, 'max_seconds', :max_seconds))
                ON CONFLICT(key) DO UPDATE SET
                  last_started_at=excluded.last_started_at,
                  last_status=excluded.last_status,
                  metadata_json=excluded.metadata_json
            '''), {'limit': limit, 'max_seconds': max_seconds})
            rows = conn.execute(text('''
                WITH universe AS (
                  SELECT lower(wallet) AS wallet, max(discovered_at) AS discovered_at
                  FROM wallet_candidates
                  WHERE active=true AND wallet ~* '^0x[0-9a-f]{40}$'
                  GROUP BY lower(wallet)
                  UNION
                  SELECT lower(wallet) AS wallet, max(qualified_at) AS discovered_at
                  FROM qualified_wallets
                  WHERE wallet ~* '^0x[0-9a-f]{40}$'
                  GROUP BY lower(wallet)
                ), deduped AS (
                  SELECT wallet, max(discovered_at) AS discovered_at
                  FROM universe
                  GROUP BY wallet
                )
                SELECT d.wallet
                FROM deduped d
                LEFT JOIN owned_wallet_metrics m ON lower(m.wallet)=d.wallet
                ORDER BY m.ts_ms ASC NULLS FIRST, d.discovered_at DESC NULLS LAST
                LIMIT :limit
            '''), {'limit': limit}).fetchall()
        wallets = [r[0] for r in rows if is_address(r[0])]
        metrics = _refresh_owned_wallet_list(wallets, max_seconds=max_seconds, run_type='owned_wallet_scanner')
        selected = select_owned_qualified_wallets() if metrics.get('wallets_ok', 0) else {'status': 'skipped', 'message': 'no wallets refreshed'}
        stats = owned_universe_stats()
        status = 'ok' if metrics.get('wallets_ok', 0) and not metrics.get('stopped_due_to_time') else 'partial'
        with engine.begin() as conn:
            conn.execute(text('''
                INSERT INTO owned_wallet_scan_state(key,last_finished_at,last_status,metadata_json)
                VALUES('main', now(), :status, CAST(:metadata AS jsonb))
                ON CONFLICT(key) DO UPDATE SET
                  last_finished_at=excluded.last_finished_at,
                  last_status=excluded.last_status,
                  metadata_json=excluded.metadata_json
            '''), {'status': status, 'metadata': json.dumps({'metrics': metrics, 'selected': selected, 'stats': stats})})
            insert_run(conn, 'owned_wallet_scanner_batch', status, f'seeded={seeded}; scanned={metrics.get("wallets_ok")}; indexed={stats.get("owned_wallets_indexed")}')
        return {
            'status': status,
            'source': 'hyperliquid_native',
            'nansen_used': False,
            'seeded_or_existing_candidates': seeded,
            'metrics': metrics,
            'selected': selected,
            'universe': stats,
        }
    finally:
        try:
            lock_conn.execute(text('SELECT pg_advisory_unlock(5525012027)'))
        except Exception:
            pass
        lock_conn.close()

def refresh_owned_wallet_metrics(limit: int | None = None, max_seconds: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    limit = int(limit or settings.owned_discovery_refresh_limit)
    max_seconds = int(max_seconds or settings.owned_refresh_max_seconds)
    with engine.begin() as conn:
        ensure_owned_tables(conn)
        rows = conn.execute(text('''
            SELECT wallet FROM (
              SELECT wallet, 0 AS priority, discovered_at AS ts FROM wallet_candidates WHERE active=true
              UNION ALL
              SELECT wallet, 1 AS priority, qualified_at AS ts FROM qualified_wallets WHERE status='active'
            ) w
            WHERE wallet ~* '^0x[0-9a-f]{40}$'
            GROUP BY wallet
            ORDER BY min(priority), max(ts) DESC NULLS LAST
            LIMIT :limit
        '''), {'limit': limit}).fetchall()
    wallets = [r[0].lower() for r in rows if is_address(r[0])]
    return _refresh_owned_wallet_list(wallets, max_seconds=max_seconds, run_type='owned_wallet_metrics')


def select_owned_qualified_wallets(limit: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    limit = int(limit or settings.qualified_wallet_limit)
    min_replacement = max(1, int(limit * settings.owned_discovery_min_replacement_ratio))
    ts = now_ms()
    with engine.begin() as conn:
        ensure_owned_tables(conn)
        qualified = conn.execute(text('''
            SELECT wallet, score
            FROM owned_wallet_metrics
            WHERE qualifies=true
            ORDER BY score DESC, account_value_usd DESC
            LIMIT :limit
        '''), {'limit': limit}).fetchall()
        existing_active = conn.execute(text("SELECT count(*) FROM qualified_wallets WHERE status='active'")).scalar() or 0
        if len(qualified) < min_replacement and existing_active >= min_replacement:
            msg = f'kept existing cohort; owned_qualified={len(qualified)} below safe threshold={min_replacement}'
            insert_run(conn, 'owned_select_qualified', 'warning', msg)
            return {'status': 'kept_existing', 'qualified': len(qualified), 'message': msg}
        if not qualified:
            msg = 'no owned qualified wallets yet; kept existing cohort'
            insert_run(conn, 'owned_select_qualified', 'warning', msg)
            return {'status': 'kept_existing', 'qualified': 0, 'message': msg}
        conn.execute(text("UPDATE qualified_wallets SET status='inactive'"))
        for rank, row in enumerate(qualified, start=1):
            conn.execute(text('''
                INSERT INTO qualified_wallets(wallet,rank,score,qualified_at_ms,status)
                VALUES(:wallet,:rank,:score,:ts,'active')
                ON CONFLICT(wallet) DO UPDATE SET
                  rank=excluded.rank,
                  score=excluded.score,
                  qualified_at=now(),
                  qualified_at_ms=excluded.qualified_at_ms,
                  status='active'
            '''), {'wallet': row[0], 'rank': rank, 'score': row[1], 'ts': ts})
        insert_run(conn, 'owned_select_qualified', 'ok', f'active_owned_wallets={len(qualified)}')
    return {'status': 'ok', 'qualified': len(qualified), 'message': f'active_owned_wallets={len(qualified)}'}


def owned_wallet_refresh(run_collection: bool | None = None) -> dict[str, Any]:
    """Nansen-free scheduled refresh for the live product.

    This job is deliberately lightweight. Live dashboard accuracy comes from
    hwt-live-events and hwt-collector-live-10s; this cron only refreshes owned
    ranking metrics/cohort selection. A Postgres advisory lock prevents two
    Render/manual cron runs from overlapping.
    """
    settings = get_settings()
    should_collect = settings.owned_refresh_run_collection if run_collection is None else bool(run_collection)

    lock_conn = engine.connect()
    try:
        got_lock = bool(lock_conn.execute(text('SELECT pg_try_advisory_lock(5525012026)')).scalar())
        if not got_lock:
            with engine.begin() as conn:
                insert_run(conn, 'owned_wallet_refresh', 'skipped', 'another owned wallet refresh is already running')
            return {
                'status': 'skipped',
                'source': 'hyperliquid_native',
                'nansen_used': False,
                'message': 'another owned wallet refresh is already running',
            }

        seeded = seed_owned_candidates()
        metrics = refresh_owned_wallet_metrics(
            limit=min(int(settings.owned_discovery_refresh_limit), int(settings.owned_refresh_limit)),
            max_seconds=int(settings.owned_refresh_max_seconds),
        )
        selected = select_owned_qualified_wallets()
        collection = collect_once() if should_collect else None
        status = 'ok' if selected.get('status') == 'ok' and not metrics.get('stopped_due_to_time') else 'partial'
        with engine.begin() as conn:
            insert_run(conn, 'owned_wallet_refresh', status, f'seeded={seeded}; metrics_ok={metrics.get("wallets_ok")}; {selected.get("message")}')
        return {
            'status': status,
            'source': 'hyperliquid_native',
            'nansen_used': False,
            'seeded_or_existing_candidates': seeded,
            'metrics': metrics,
            'selected': selected,
            'collection': collection,
        }
    finally:
        try:
            lock_conn.execute(text('SELECT pg_advisory_unlock(5525012026)'))
        except Exception:
            pass
        lock_conn.close()

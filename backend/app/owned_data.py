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
    return (
        account >= settings.owned_discovery_min_account_value_usd
        and pnl30 >= settings.owned_discovery_min_30d_pnl_usd
        and safe_float(score_row.get('pnl_all_time_usd')) >= settings.owned_discovery_min_all_time_pnl_usd
        and safe_float(score_row.get('score')) >= settings.owned_discovery_min_score
        and int(fill_summary.get('fills_lookback_count') or 0) >= settings.owned_discovery_min_fills_lookback
    )


def refresh_owned_wallet(wallet: str, lookback_days: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    lookback_days = int(lookback_days or settings.owned_discovery_lookback_days)
    hl = Hyperliquid()
    state = hl.clearinghouse_state(wallet)
    portfolio = hl.portfolio(wallet)
    fills: list[dict[str, Any]] = []
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


def refresh_owned_wallet_metrics(limit: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    limit = int(limit or settings.owned_discovery_refresh_limit)
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
    ok = 0
    errors: list[str] = []
    started = time.time()
    for i, wallet in enumerate(wallets, start=1):
        log.info('Owned wallet metrics %s/%s %s', i, len(wallets), wallet)
        try:
            refresh_owned_wallet(wallet)
            ok += 1
        except Exception as exc:
            log.exception('owned wallet refresh failed %s', wallet)
            errors.append(f'{wallet}: {str(exc)[:160]}')
        time.sleep(max(0.0, float(settings.owned_discovery_request_delay_seconds)))
    with engine.begin() as conn:
        insert_run(conn, 'owned_wallet_metrics', 'ok' if not errors else 'partial', f'ok={ok}; errors={len(errors)}; elapsed={time.time()-started:.1f}s')
    return {'wallets_checked': len(wallets), 'wallets_ok': ok, 'errors': errors[:10], 'elapsed_seconds': round(time.time() - started, 1)}


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


def owned_wallet_refresh(run_collection: bool = True) -> dict[str, Any]:
    """Nansen-free daily refresh for the live product."""
    seeded = seed_owned_candidates()
    metrics = refresh_owned_wallet_metrics()
    selected = select_owned_qualified_wallets()
    collection = collect_once() if run_collection else None
    status = 'ok' if selected.get('status') == 'ok' else 'partial'
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

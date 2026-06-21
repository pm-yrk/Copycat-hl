from __future__ import annotations

import logging
import os
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _table_exists(conn, table_name: str) -> bool:
    try:
        return bool(conn.execute(text("""
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name=:table_name
            ) AS exists
        """), {'table_name': table_name}).scalar())
    except Exception:
        return False


def _delete(conn, label: str, sql: str, params: dict[str, Any] | None = None) -> int:
    params = params or {}
    try:
        result = conn.execute(text(sql), params)
        rows = int(result.rowcount or 0)
        log.info('Database diet: %s deleted=%s', label, rows)
        return rows
    except SQLAlchemyError as exc:
        log.warning('Database diet skipped %s: %s', label, exc)
        return 0


def _vacuum(table_names: list[str]) -> None:
    if not _env_bool('COPYCAT_DIET_VACUUM_FULL', False):
        return
    # VACUUM FULL physically gives disk space back to Supabase, but it locks each table.
    # Keep it opt-in and normally run it manually/off-peak.
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
        for name in table_names:
            if _table_exists(conn, name):
                try:
                    log.info('Database diet: VACUUM FULL %s', name)
                    conn.execute(text(f'VACUUM FULL public.{name}'))
                except SQLAlchemyError as exc:
                    log.warning('Database diet vacuum skipped %s: %s', name, exc)


def run_database_diet() -> dict[str, Any]:
    """Keep Supabase Free viable by treating Postgres as hot/current storage only.

    Defaults are deliberately aggressive. Copycat's dashboard only needs current
    positions/snapshots plus short recent history for flow/change calculations.
    Long-term raw history should not live in Supabase Free.
    """
    started = time.time()
    positions_keep_snapshots = max(1, _env_int('COPYCAT_POSITIONS_KEEP_SNAPSHOTS', 6))
    wallet_keep_per_wallet = max(1, _env_int('COPYCAT_WALLET_SNAPSHOTS_KEEP_PER_WALLET', 6))
    asset_signal_keep_snapshots = max(10, _env_int('COPYCAT_ASSET_SIGNALS_KEEP_SNAPSHOTS', 288))
    portfolio_keep_snapshots = max(10, _env_int('COPYCAT_PORTFOLIO_TARGETS_KEEP_SNAPSHOTS', 288))
    market_keep_rows = max(100, _env_int('COPYCAT_MARKET_SNAPSHOTS_KEEP_ROWS', 2000))
    metric_keep_rows = max(100, _env_int('COPYCAT_METRIC_HISTORY_KEEP_ROWS', 2000))
    live_events_keep_days = max(1, _env_int('COPYCAT_LIVE_EVENTS_KEEP_DAYS', 2))
    fills_keep_days = max(0, _env_int('COPYCAT_OWNED_FILLS_KEEP_DAYS', 14))
    strategy_keep_rows = max(100, _env_int('COPYCAT_STRATEGY_POINTS_KEEP_ROWS', 5000))
    runs_keep_rows = max(50, _env_int('COPYCAT_COLLECTOR_RUNS_KEEP_ROWS', 500))

    deleted: dict[str, int] = {}
    with engine.begin() as conn:
        if _table_exists(conn, 'positions'):
            deleted['positions'] = _delete(conn, 'positions older snapshots', """
                WITH keep AS (
                  SELECT ts_ms FROM (
                    SELECT DISTINCT ts_ms FROM positions ORDER BY ts_ms DESC LIMIT :keep_n
                  ) k
                )
                DELETE FROM positions p
                WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = p.ts_ms)
            """, {'keep_n': positions_keep_snapshots})

        if _table_exists(conn, 'wallet_snapshots'):
            deleted['wallet_snapshots'] = _delete(conn, 'wallet_snapshots per wallet', """
                WITH ranked AS (
                  SELECT id, row_number() OVER (PARTITION BY wallet ORDER BY ts_ms DESC, id DESC) AS rn
                  FROM wallet_snapshots
                )
                DELETE FROM wallet_snapshots ws
                USING ranked r
                WHERE ws.id = r.id AND r.rn > :keep_n
            """, {'keep_n': wallet_keep_per_wallet})

        if _table_exists(conn, 'asset_signals'):
            deleted['asset_signals'] = _delete(conn, 'asset_signals older snapshots', """
                WITH keep AS (
                  SELECT ts_ms FROM (
                    SELECT DISTINCT ts_ms FROM asset_signals ORDER BY ts_ms DESC LIMIT :keep_n
                  ) k
                )
                DELETE FROM asset_signals a
                WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = a.ts_ms)
            """, {'keep_n': asset_signal_keep_snapshots})

        if _table_exists(conn, 'portfolio_targets'):
            deleted['portfolio_targets'] = _delete(conn, 'portfolio_targets older snapshots', """
                WITH keep AS (
                  SELECT ts_ms FROM (
                    SELECT DISTINCT ts_ms FROM portfolio_targets ORDER BY ts_ms DESC LIMIT :keep_n
                  ) k
                )
                DELETE FROM portfolio_targets p
                WHERE NOT EXISTS (SELECT 1 FROM keep WHERE keep.ts_ms = p.ts_ms)
            """, {'keep_n': portfolio_keep_snapshots})

        if _table_exists(conn, 'copycat_market_snapshots'):
            deleted['copycat_market_snapshots'] = _delete(conn, 'copycat_market_snapshots old rows', """
                DELETE FROM copycat_market_snapshots cms
                WHERE id IN (
                  SELECT id FROM copycat_market_snapshots ORDER BY ts_ms DESC OFFSET :keep_n
                )
            """, {'keep_n': market_keep_rows})

        if _table_exists(conn, 'owned_wallet_metric_history'):
            deleted['owned_wallet_metric_history'] = _delete(conn, 'owned_wallet_metric_history old rows', """
                DELETE FROM owned_wallet_metric_history h
                WHERE id IN (
                  SELECT id FROM owned_wallet_metric_history ORDER BY ts_ms DESC OFFSET :keep_n
                )
            """, {'keep_n': metric_keep_rows})

        if _table_exists(conn, 'strategy_index_points'):
            deleted['strategy_index_points'] = _delete(conn, 'strategy_index_points old rows', """
                DELETE FROM strategy_index_points s
                WHERE id IN (
                  SELECT id FROM strategy_index_points ORDER BY ts_ms DESC OFFSET :keep_n
                )
            """, {'keep_n': strategy_keep_rows})

        if _table_exists(conn, 'collector_runs'):
            deleted['collector_runs'] = _delete(conn, 'collector_runs old rows', """
                DELETE FROM collector_runs c
                WHERE id IN (
                  SELECT id FROM collector_runs ORDER BY ts_ms DESC OFFSET :keep_n
                )
            """, {'keep_n': runs_keep_rows})

        if _table_exists(conn, 'copycat_live_events'):
            cutoff_ms = int((time.time() - live_events_keep_days * 86400) * 1000)
            deleted['copycat_live_events'] = _delete(conn, 'copycat_live_events old rows', """
                DELETE FROM copycat_live_events WHERE ts_ms < :cutoff_ms
            """, {'cutoff_ms': cutoff_ms})

        if fills_keep_days == 0 and _table_exists(conn, 'owned_wallet_fills'):
            deleted['owned_wallet_fills'] = _delete(conn, 'owned_wallet_fills disabled hot history', """
                DELETE FROM owned_wallet_fills
            """)
        elif _table_exists(conn, 'owned_wallet_fills'):
            cutoff_ms = int((time.time() - fills_keep_days * 86400) * 1000)
            deleted['owned_wallet_fills'] = _delete(conn, 'owned_wallet_fills old rows', """
                DELETE FROM owned_wallet_fills WHERE ts_ms < :cutoff_ms
            """, {'cutoff_ms': cutoff_ms})

    vacuum_tables = [name for name, count in deleted.items() if count > 0]
    _vacuum(vacuum_tables)
    elapsed = round(time.time() - started, 2)
    log.info('Database diet complete elapsed=%ss deleted=%s', elapsed, deleted)
    return {'status': 'ok', 'elapsed_seconds': elapsed, 'deleted': deleted}


def strip_raw_json_rows(snapshot_rows: list[dict[str, Any]], position_rows: list[dict[str, Any]]) -> None:
    """Avoid storing huge Hyperliquid raw JSON blobs in hot Supabase tables."""
    if _env_bool('COPYCAT_STORE_RAW_JSON', False):
        return
    for row in snapshot_rows:
        row['raw_json'] = '{}'
    for row in position_rows:
        row['raw_json'] = '{}'


def maybe_run_database_diet_after_collect() -> None:
    if not _env_bool('COPYCAT_PRUNE_AFTER_COLLECT', True):
        return
    try:
        run_database_diet()
    except Exception as exc:
        # Diet failure must never break live dashboard collection.
        log.warning('Database diet after collect skipped: %s', exc)

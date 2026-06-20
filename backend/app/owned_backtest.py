from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from .backtest import _fetch_benchmarks, _ms, _normalised_nav, _price_on_or_before
from .db import engine
from .settings import get_settings
from .worker import insert_run, safe_float
from .owned_data import ensure_owned_tables

log = logging.getLogger(__name__)

_METHOD = 'copycat_owned_backtest_v1_weekly'
_FEE_SLIPPAGE_RATE = 0.0015


def _date_from_ms(ts_ms: int) -> date:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).date()


def _week_floor(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _available_range(conn) -> tuple[date | None, date | None]:
    row = conn.execute(text('SELECT min(ts_ms) AS min_ts, max(ts_ms) AS max_ts FROM owned_wallet_metric_history')).mappings().first()
    if not row or not row.get('min_ts') or not row.get('max_ts'):
        return None, None
    return _date_from_ms(int(row['min_ts'])), _date_from_ms(int(row['max_ts']))


def _ranges(start: date, end: date, rebalance_days: int) -> list[tuple[date, date]]:
    cur = _week_floor(start)
    out: list[tuple[date, date]] = []
    while cur + timedelta(days=rebalance_days) <= end:
        nxt = cur + timedelta(days=rebalance_days)
        out.append((cur, nxt))
        cur = nxt
    return out


def _cohort_at(conn, ts_ms: int, limit: int, min_wallets: int) -> list[dict[str, Any]]:
    rows = conn.execute(text('''
        WITH latest AS (
          SELECT DISTINCT ON(wallet)
            wallet, account_value_usd, score, ts_ms
          FROM owned_wallet_metric_history
          WHERE ts_ms <= :ts_ms AND qualifies=true AND account_value_usd > 0
          ORDER BY wallet, ts_ms DESC
        )
        SELECT wallet, account_value_usd, score
        FROM latest
        ORDER BY score DESC, account_value_usd DESC
        LIMIT :limit
    '''), {'ts_ms': ts_ms, 'limit': limit}).mappings().all()
    cohort = [dict(r) for r in rows]
    if len(cohort) < min_wallets:
        return []
    return cohort


def _cohort_week_return(conn, cohort: list[dict[str, Any]], start_ms: int, end_ms: int) -> tuple[float | None, dict[str, Any]]:
    wallets = [c['wallet'] for c in cohort]
    capital = sum(max(safe_float(c.get('account_value_usd')), 1.0) for c in cohort)
    if not wallets or capital <= 0:
        return None, {'reason': 'empty_cohort'}
    fills = conn.execute(text('''
        SELECT COALESCE(sum(closed_pnl_usd),0) AS closed_pnl,
               COALESCE(sum(abs(fee_usd)),0) AS fees,
               count(*) AS fills
        FROM owned_wallet_fills
        WHERE wallet = ANY(:wallets)
          AND ts_ms >= :start_ms
          AND ts_ms < :end_ms
    '''), {'wallets': wallets, 'start_ms': start_ms, 'end_ms': end_ms}).mappings().first() or {}
    closed_pnl = safe_float(fills.get('closed_pnl'))
    fees = abs(safe_float(fills.get('fees')))
    net_pnl = closed_pnl - fees
    raw = net_pnl / max(capital, 1.0)
    clipped = max(-0.85, min(1.50, raw))
    return clipped - _FEE_SLIPPAGE_RATE, {
        'cohort_wallets': len(cohort),
        'capital_usd': capital,
        'closed_pnl_usd': closed_pnl,
        'fees_usd': fees,
        'fills': int(fills.get('fills') or 0),
        'raw_weekly_return': raw,
        'fee_slippage_rate': _FEE_SLIPPAGE_RATE,
        'clipped': clipped != raw,
    }


def run_owned_backtest_from_history(dry_run: bool = False) -> dict[str, Any]:
    """Build the public backtest table from Copycat's own stored Hyperliquid data.

    This does not call Nansen. It only works once enough owned_wallet_metric_history
    and owned_wallet_fills have accumulated.
    """
    settings = get_settings()
    min_rows = int(settings.owned_backtest_min_rows)
    min_wallets = int(settings.owned_backtest_min_wallets)
    rebalance_days = int(settings.owned_backtest_rebalance_days)
    limit = int(settings.qualified_wallet_limit)

    with engine.begin() as conn:
        ensure_owned_tables(conn)
        start, end = _available_range(conn)
        if not start or not end:
            msg = 'No owned metric history yet. Nansen was not used.'
            insert_run(conn, 'copycat_owned_backtest', 'waiting', msg)
            return {'status': 'waiting', 'message': msg, 'rows_written': 0}

    windows = _ranges(start, end, rebalance_days)
    if len(windows) < min_rows:
        msg = f'Only {len(windows)} owned history windows available; need {min_rows}. Nansen was not used.'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_owned_backtest', 'waiting', msg)
        return {'status': 'waiting', 'message': msg, 'rows_written': 0, 'windows_available': len(windows)}

    bench_start = windows[0][0]
    bench_end = windows[-1][1]
    btc, eth, spx = _fetch_benchmarks(bench_start, bench_end)
    btc_base = _price_on_or_before(btc, bench_start)
    eth_base = _price_on_or_before(eth, bench_start)
    spx_base = _price_on_or_before(spx, bench_start)

    nav = 100.0
    points: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    with engine.begin() as conn:
        for start_d, end_d in windows:
            start_ms = _ms(start_d)
            end_ms = _ms(end_d)
            cohort = _cohort_at(conn, start_ms, limit, min_wallets)
            if not cohort:
                skipped.append({'from': start_d.isoformat(), 'to': end_d.isoformat(), 'reason': 'not_enough_qualified_wallets'})
                continue
            weekly_return, meta = _cohort_week_return(conn, cohort, start_ms, end_ms)
            if weekly_return is None:
                skipped.append({'from': start_d.isoformat(), 'to': end_d.isoformat(), **meta})
                continue
            nav *= max(0.0, 1.0 + weekly_return)
            btc_px = _price_on_or_before(btc, end_d)
            eth_px = _price_on_or_before(eth, end_d)
            spx_px = _price_on_or_before(spx, end_d)
            points.append({
                'ts_ms': end_ms,
                'copycat_nav': nav,
                'btc_nav': _normalised_nav(btc_px, btc_base),
                'eth_nav': _normalised_nav(eth_px, eth_base),
                'spx_nav': _normalised_nav(spx_px, spx_base),
                'metadata': {
                    'period_from': start_d.isoformat(),
                    'period_to': end_d.isoformat(),
                    'source': 'copycat_owned_hyperliquid_data',
                    'benchmark_source': 'Hyperliquid daily candles for BTC/ETH; Stooq daily close for S&P 500',
                    'method_note': 'Weekly backtest from Copycat-owned Hyperliquid fills and stored wallet ranking history. Not live performance and not a guarantee of future results.',
                    **meta,
                },
            })

    if len(points) < min_rows:
        msg = f'Only {len(points)} owned backtest rows passed validation; need {min_rows}. Nansen was not used.'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_owned_backtest', 'waiting', msg)
        return {'status': 'waiting', 'message': msg, 'rows_written': 0, 'points_ready': len(points), 'skipped': skipped[:20]}

    if dry_run:
        return {'status': 'dry_run_ok', 'rows_ready': len(points), 'first_ts_ms': points[0]['ts_ms'], 'last_ts_ms': points[-1]['ts_ms'], 'skipped': skipped[:20]}

    with engine.begin() as conn:
        conn.execute(text('''
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
        '''))
        if settings.owned_backtest_replace_existing:
            conn.execute(text('DELETE FROM strategy_backtest_points'))
        for p in points:
            conn.execute(text('''
                INSERT INTO strategy_backtest_points(
                    ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav,
                    copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct,
                    method, metadata_json
                ) VALUES (
                    :ts_ms, :copycat_nav, :btc_nav, :eth_nav, :spx_nav,
                    :copycat_return_pct, :btc_return_pct, :eth_return_pct, :spx_return_pct,
                    :method, CAST(:metadata_json AS jsonb)
                )
                ON CONFLICT(ts_ms) DO UPDATE SET
                  copycat_nav=excluded.copycat_nav,
                  btc_nav=excluded.btc_nav,
                  eth_nav=excluded.eth_nav,
                  spx_nav=excluded.spx_nav,
                  copycat_return_pct=excluded.copycat_return_pct,
                  btc_return_pct=excluded.btc_return_pct,
                  eth_return_pct=excluded.eth_return_pct,
                  spx_return_pct=excluded.spx_return_pct,
                  method=excluded.method,
                  metadata_json=excluded.metadata_json
            '''), {
                'ts_ms': p['ts_ms'],
                'copycat_nav': float(p['copycat_nav']),
                'btc_nav': float(p['btc_nav']),
                'eth_nav': float(p['eth_nav']),
                'spx_nav': float(p['spx_nav']),
                'copycat_return_pct': float(p['copycat_nav']) - 100.0,
                'btc_return_pct': float(p['btc_nav']) - 100.0,
                'eth_return_pct': float(p['eth_nav']) - 100.0,
                'spx_return_pct': float(p['spx_nav']) - 100.0,
                'method': _METHOD,
                'metadata_json': json.dumps(p.get('metadata') or {}),
            })
        insert_run(conn, 'copycat_owned_backtest', 'ok', f'wrote {len(points)} rows; skipped={len(skipped)}')
    return {'status': 'ok', 'rows_written': len(points), 'skipped_windows': len(skipped), 'method': _METHOD}

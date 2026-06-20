from __future__ import annotations

import csv
import io
import json
import logging
import math
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .db import engine
from .settings import get_settings
from .worker import Nansen, extract_records, find_address, insert_run, safe_float

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

_METHOD = 'copycat_backtest_v1_weekly_nansen_pnl_proxy'
_FEE_SLIPPAGE_RATE = 0.0015


class BacktestBlocked(RuntimeError):
    """Raised when a required external data source is unavailable."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def _date_from_ms(ts_ms: int) -> date:
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date()


def _ensure_backtest_table(conn) -> None:
    conn.execute(text("""
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
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_strategy_backtest_points_ts ON strategy_backtest_points(ts_ms DESC)"))


def _nested_values(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _nested_values(v)
    elif isinstance(obj, list):
        for item in obj[:25]:
            yield from _nested_values(item)


def _first_number_by_keys(obj: Any, keys: tuple[str, ...]) -> float | None:
    wanted = {k.lower().replace('_', '') for k in keys}
    for key, value in _nested_values(obj):
        norm = key.lower().replace('_', '')
        if norm in wanted:
            val = safe_float(value, None)
            if val is not None and math.isfinite(val):
                return float(val)
    return None


def _record_pnl_usd(record: dict[str, Any]) -> float | None:
    return _first_number_by_keys(record, (
        'total_pnl', 'totalPnl', 'realized_pnl', 'realizedPnl', 'net_pnl', 'netPnl',
        'pnl', 'profit', 'closed_pnl', 'closedPnl', 'perp_pnl', 'perpPnl',
    ))


def _record_account_value_usd(record: dict[str, Any]) -> float | None:
    return _first_number_by_keys(record, (
        'account_value', 'accountValue', 'account_value_usd', 'accountValueUsd',
        'equity', 'aum', 'portfolio_value', 'portfolioValue', 'margin_summary_account_value',
    ))


def _nansen_blocked_message(exc: Exception) -> str | None:
    msg = str(exc)
    if 'Nansen HTTP 403' in msg or 'Insufficient credits' in msg:
        return 'Nansen is blocked: insufficient credits. Existing backtest rows were left unchanged.'
    if 'NANSEN_API_KEY missing' in msg:
        return 'Nansen is blocked: NANSEN_API_KEY is missing. Existing backtest rows were left unchanged.'
    return None


def _week_ranges(days: int, rebalance_days: int) -> list[tuple[date, date]]:
    today = date.today()
    start = today - timedelta(days=max(days, rebalance_days))
    # Start on a clean rebalance interval and end no later than today.
    ranges: list[tuple[date, date]] = []
    cur = start
    while cur + timedelta(days=rebalance_days) <= today:
        end = cur + timedelta(days=rebalance_days)
        ranges.append((cur, end))
        cur = end
    return ranges


def _hl_candles(symbol: str, start: date, end: date) -> dict[date, float]:
    start_ms = _ms(start)
    end_ms = _ms(end + timedelta(days=1))
    payload = {
        'type': 'candleSnapshot',
        'req': {'coin': symbol.upper(), 'interval': '1d', 'startTime': start_ms, 'endTime': end_ms},
    }
    req = urllib.request.Request(
        get_settings().hl_info_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': 'CopycatBacktest/1.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=25) as res:
        raw = json.loads(res.read().decode('utf-8'))
    out: dict[date, float] = {}
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            ts = int(safe_float(row.get('t') or row.get('T')))
            close = safe_float(row.get('c') or row.get('close'))
            if ts > 0 and close > 0:
                out[_date_from_ms(ts)] = close
    return out


def _stooq_spx(start: date, end: date) -> dict[date, float]:
    d1 = start.strftime('%Y%m%d')
    d2 = end.strftime('%Y%m%d')
    url = f'https://stooq.com/q/d/l/?s=%5Espx&i=d&d1={d1}&d2={d2}'
    with urllib.request.urlopen(url, timeout=20) as res:
        body = res.read().decode('utf-8', errors='replace')
    out: dict[date, float] = {}
    for row in csv.DictReader(io.StringIO(body)):
        try:
            d = datetime.strptime(row.get('Date') or '', '%Y-%m-%d').date()
        except Exception:
            continue
        close = safe_float(row.get('Close'))
        if close > 0:
            out[d] = close
    return out


def _price_on_or_before(series: dict[date, float], d: date) -> float | None:
    cur = d
    for _ in range(10):
        px = series.get(cur)
        if px and px > 0:
            return float(px)
        cur -= timedelta(days=1)
    return None


def _fetch_benchmarks(start: date, end: date) -> tuple[dict[date, float], dict[date, float], dict[date, float]]:
    btc = _hl_candles('BTC', start, end)
    eth = _hl_candles('ETH', start, end)
    spx = _stooq_spx(start, end)
    return btc, eth, spx


def _fetch_nansen_week(client: Nansen, start: date, end: date, max_candidates: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = max(1, math.ceil(max_candidates / 100))
    for page in range(1, pages + 1):
        log.info('Backtest Nansen leaderboard %s to %s page %s/%s', start, end, page, pages)
        payload = client.leaderboard(page=page, per_page=100, start=start, end=end)
        records = extract_records(payload)
        if not records:
            break
        for rec in records:
            wallet = find_address(rec) or f'unknown:{len(rows)}'
            if wallet in seen:
                continue
            seen.add(wallet)
            pnl = _record_pnl_usd(rec)
            account = _record_account_value_usd(rec)
            if pnl is None or account is None or account <= 0:
                continue
            rows.append({'wallet': wallet, 'pnl_usd': float(pnl), 'account_value_usd': float(account), 'raw': rec})
            if len(rows) >= max_candidates:
                break
        if len(rows) >= max_candidates:
            break
        time.sleep(0.25)
    return rows


def _cohort_return(rows: list[dict[str, Any]], min_wallets: int) -> tuple[float | None, dict[str, Any]]:
    usable = [r for r in rows if abs(safe_float(r.get('pnl_usd'))) > 0 and safe_float(r.get('account_value_usd')) > 0]
    if len(usable) < min_wallets:
        return None, {'usable_wallets': len(usable), 'reason': 'not_enough_usable_wallets'}
    pnl = sum(safe_float(r.get('pnl_usd')) for r in usable)
    capital = sum(max(safe_float(r.get('account_value_usd')), 1.0) for r in usable)
    raw = pnl / max(capital, 1.0)
    # Guardrail against parsing or provider anomalies. A weekly cohort move beyond
    # these bounds needs manual review before being used in marketing.
    clipped = max(-0.85, min(1.50, raw))
    return clipped - _FEE_SLIPPAGE_RATE, {
        'usable_wallets': len(usable),
        'total_pnl_usd': pnl,
        'total_account_value_usd': capital,
        'raw_weekly_return': raw,
        'fee_slippage_rate': _FEE_SLIPPAGE_RATE,
        'clipped': clipped != raw,
    }


def _normalised_nav(price: float | None, base_price: float | None) -> float:
    if not price or not base_price or price <= 0 or base_price <= 0:
        return 100.0
    return 100.0 * (price / base_price)


def run_backtest(days: int | None = None, rebalance_days: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Build the public 1Y backtest table from real Nansen weekly cohort data.

    This is a wallet-cohort PnL proxy backtest. It is intentionally not presented
    as live performance and it never fabricates rows. If Nansen credits are blocked,
    the job exits cleanly and leaves any existing backtest rows untouched.
    """
    settings = get_settings()
    if not settings.nansen_api_key:
        msg = 'Nansen is blocked: NANSEN_API_KEY is missing. Existing backtest rows were left unchanged.'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_backtest', 'blocked', msg)
        return {'status': 'blocked', 'message': msg, 'rows_written': 0}

    days = int(days or settings.nansen_backtest_days)
    rebalance_days = int(rebalance_days or settings.nansen_backtest_rebalance_days)
    ranges = _week_ranges(days, rebalance_days)
    if len(ranges) < 4:
        return {'status': 'error', 'message': 'Not enough rebalance windows.', 'rows_written': 0}

    start = ranges[0][0]
    end = ranges[-1][1]
    log.info('Fetching benchmark history %s to %s', start, end)
    try:
        btc_series, eth_series, spx_series = _fetch_benchmarks(start, end)
    except Exception as exc:
        msg = f'Benchmark history fetch failed: {str(exc)[:300]}'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_backtest', 'error', msg)
        return {'status': 'error', 'message': msg, 'rows_written': 0}

    btc_base = _price_on_or_before(btc_series, start)
    eth_base = _price_on_or_before(eth_series, start)
    spx_base = _price_on_or_before(spx_series, start)
    client = Nansen()
    nav = 100.0
    points: list[dict[str, Any]] = [{
        'ts_ms': _ms(start),
        'copycat_nav': 100.0,
        'btc_nav': 100.0,
        'eth_nav': 100.0,
        'spx_nav': 100.0,
        'metadata': {'event': 'baseline', 'method_note': 'Nansen weekly wallet-cohort PnL proxy backtest'},
    }]
    skipped: list[dict[str, Any]] = []

    try:
        for start_d, end_d in ranges:
            rows = _fetch_nansen_week(client, start_d, end_d, int(settings.nansen_backtest_max_candidates))
            weekly_return, meta = _cohort_return(rows, int(settings.nansen_backtest_min_wallets))
            if weekly_return is None:
                skipped.append({'from': start_d.isoformat(), 'to': end_d.isoformat(), **meta})
                continue
            nav = max(0.0, nav * (1.0 + weekly_return))
            btc_px = _price_on_or_before(btc_series, end_d)
            eth_px = _price_on_or_before(eth_series, end_d)
            spx_px = _price_on_or_before(spx_series, end_d)
            points.append({
                'ts_ms': _ms(end_d),
                'copycat_nav': nav,
                'btc_nav': _normalised_nav(btc_px, btc_base),
                'eth_nav': _normalised_nav(eth_px, eth_base),
                'spx_nav': _normalised_nav(spx_px, spx_base),
                'metadata': {
                    'period_from': start_d.isoformat(),
                    'period_to': end_d.isoformat(),
                    'weekly_return': weekly_return,
                    'source': 'nansen_perp_leaderboard',
                    'benchmark_source': 'Hyperliquid daily candles for BTC/ETH; Stooq daily close for S&P 500',
                    'method_note': 'Weekly Nansen wallet-cohort PnL proxy. Not live performance and not a guarantee of future results.',
                    **meta,
                },
            })
            time.sleep(0.25)
    except Exception as exc:
        blocked = _nansen_blocked_message(exc)
        status = 'blocked' if blocked else 'error'
        msg = blocked or f'Backtest failed before completion: {str(exc)[:300]}'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_backtest', status, msg)
        return {'status': status, 'message': msg, 'rows_written': 0, 'points_ready': len(points), 'skipped': skipped[:10]}

    min_rows = int(settings.nansen_backtest_min_rows)
    if len(points) < min_rows:
        msg = f'Only {len(points)} backtest rows passed validation; need at least {min_rows}. Existing rows left unchanged.'
        with engine.begin() as conn:
            insert_run(conn, 'copycat_backtest', 'blocked', msg)
        return {'status': 'blocked', 'message': msg, 'rows_written': 0, 'points_ready': len(points), 'skipped': skipped[:20]}

    if dry_run:
        return {'status': 'dry_run_ok', 'rows_ready': len(points), 'first_ts_ms': points[0]['ts_ms'], 'last_ts_ms': points[-1]['ts_ms'], 'skipped': skipped[:20]}

    with engine.begin() as conn:
        _ensure_backtest_table(conn)
        if settings.nansen_backtest_replace_existing:
            conn.execute(text('DELETE FROM strategy_backtest_points'))
        for p in points:
            copycat_nav = float(p['copycat_nav'])
            btc_nav = float(p['btc_nav'])
            eth_nav = float(p['eth_nav'])
            spx_nav = float(p['spx_nav'])
            conn.execute(text("""
                INSERT INTO strategy_backtest_points(
                    ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav,
                    copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct,
                    method, metadata_json
                ) VALUES (
                    :ts_ms, :copycat_nav, :btc_nav, :eth_nav, :spx_nav,
                    :copycat_return_pct, :btc_return_pct, :eth_return_pct, :spx_return_pct,
                    :method, CAST(:metadata_json AS jsonb)
                )
                ON CONFLICT (ts_ms) DO UPDATE SET
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
            """), {
                'ts_ms': p['ts_ms'],
                'copycat_nav': copycat_nav,
                'btc_nav': btc_nav,
                'eth_nav': eth_nav,
                'spx_nav': spx_nav,
                'copycat_return_pct': copycat_nav - 100.0,
                'btc_return_pct': btc_nav - 100.0,
                'eth_return_pct': eth_nav - 100.0,
                'spx_return_pct': spx_nav - 100.0,
                'method': _METHOD,
                'metadata_json': json.dumps(p.get('metadata') or {}),
            })
        insert_run(conn, 'copycat_backtest', 'ok', f'wrote {len(points)} rows; skipped={len(skipped)}')

    return {'status': 'ok', 'rows_written': len(points), 'skipped_windows': len(skipped), 'method': _METHOD}


def import_backtest_csv(path: str) -> dict[str, Any]:
    """Import externally validated backtest rows.

    Required CSV columns: date, copycat_nav, btc_nav, eth_nav, spx_nav.
    This gives a safe manual route if Nansen API credits are unavailable but a
    validated export has been prepared elsewhere.
    """
    rows: list[dict[str, Any]] = []
    p = Path(path).expanduser().resolve()
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            d_raw = (row.get('date') or row.get('ts') or '').strip()
            try:
                d = datetime.fromisoformat(d_raw.replace('Z', '+00:00')).date()
            except Exception:
                d = datetime.strptime(d_raw, '%Y-%m-%d').date()
            if d > date.today():
                raise ValueError(f'CSV contains future date: {d.isoformat()}')
            item = {
                'ts_ms': _ms(d),
                'copycat_nav': safe_float(row.get('copycat_nav'), None),
                'btc_nav': safe_float(row.get('btc_nav'), None),
                'eth_nav': safe_float(row.get('eth_nav'), None),
                'spx_nav': safe_float(row.get('spx_nav'), None),
                'metadata': {'source': 'manual_validated_csv', 'date': d.isoformat()},
            }
            if any(item[k] is None or item[k] <= 0 for k in ('copycat_nav', 'btc_nav', 'eth_nav', 'spx_nav')):
                raise ValueError(f'CSV row has invalid NAV values for {d.isoformat()}')
            rows.append(item)
    rows.sort(key=lambda x: x['ts_ms'])
    if len(rows) < 2:
        raise ValueError('CSV must contain at least 2 rows')
    with engine.begin() as conn:
        _ensure_backtest_table(conn)
        conn.execute(text('DELETE FROM strategy_backtest_points'))
        for item in rows:
            conn.execute(text("""
                INSERT INTO strategy_backtest_points(
                    ts_ms, copycat_nav, btc_nav, eth_nav, spx_nav,
                    copycat_return_pct, btc_return_pct, eth_return_pct, spx_return_pct,
                    method, metadata_json
                ) VALUES (
                    :ts_ms, :copycat_nav, :btc_nav, :eth_nav, :spx_nav,
                    :copycat_return_pct, :btc_return_pct, :eth_return_pct, :spx_return_pct,
                    :method, CAST(:metadata_json AS jsonb)
                )
                ON CONFLICT (ts_ms) DO UPDATE SET
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
            """), {
                **item,
                'copycat_return_pct': float(item['copycat_nav']) - 100.0,
                'btc_return_pct': float(item['btc_nav']) - 100.0,
                'eth_return_pct': float(item['eth_nav']) - 100.0,
                'spx_return_pct': float(item['spx_nav']) - 100.0,
                'method': 'copycat_backtest_manual_validated_csv',
                'metadata_json': json.dumps(item['metadata']),
            })
        insert_run(conn, 'copycat_backtest_import', 'ok', f'imported {len(rows)} rows from CSV')
    return {'status': 'ok', 'rows_written': len(rows), 'method': 'copycat_backtest_manual_validated_csv'}

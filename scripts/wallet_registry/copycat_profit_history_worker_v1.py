#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

INFO_URL = "https://api.hyperliquid.xyz/info"
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ZERO_ADDRESS = "0x" + ("0" * 40)
LOOKBACK_DAYS = 90
MAX_FILL_PAGES = 5
MAX_API_FILLS = 10_000
NORMAL_RESCAN_HOURS = 7 * 24
LIVE_RESCAN_HOURS = 24


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text(value: dt.datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except Exception:
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def valid_wallet(value: Any) -> bool:
    address = str(value or "").strip().lower()
    return bool(ADDRESS_RE.fullmatch(address)) and address != ZERO_ADDRESS


def parse_utc(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def post_info(body: dict[str, Any], timeout: int = 25, retries: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            INFO_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CopycatProfitHistory/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if 500 <= exc.code < 600:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except Exception as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(str(last_error or "Hyperliquid request failed"))


def connect_db(repo: Path) -> sqlite3.Connection:
    path = repo / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite"
    if not path.exists():
        raise FileNotFoundError(path)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS wallet_profit_metrics (
            address TEXT PRIMARY KEY,
            observed_at_utc TEXT NOT NULL,
            lookback_days INTEGER NOT NULL,
            first_fill_ms INTEGER NOT NULL DEFAULT 0,
            last_fill_ms INTEGER NOT NULL DEFAULT 0,
            span_days REAL NOT NULL DEFAULT 0,
            fill_count INTEGER NOT NULL DEFAULT 0,
            active_days INTEGER NOT NULL DEFAULT 0,
            observed_weeks INTEGER NOT NULL DEFAULT 0,
            profitable_weeks INTEGER NOT NULL DEFAULT 0,
            profitable_week_ratio REAL NOT NULL DEFAULT 0,
            winning_fills INTEGER NOT NULL DEFAULT 0,
            losing_fills INTEGER NOT NULL DEFAULT 0,
            win_rate REAL NOT NULL DEFAULT 0,
            gross_profit REAL NOT NULL DEFAULT 0,
            gross_loss REAL NOT NULL DEFAULT 0,
            closed_pnl REAL NOT NULL DEFAULT 0,
            fees REAL NOT NULL DEFAULT 0,
            funding REAL NOT NULL DEFAULT 0,
            net_pnl REAL NOT NULL DEFAULT 0,
            largest_win_share REAL NOT NULL DEFAULT 1,
            worst_day_loss REAL NOT NULL DEFAULT 0,
            account_value REAL NOT NULL DEFAULT 0,
            position_value REAL NOT NULL DEFAULT 0,
            open_positions INTEGER NOT NULL DEFAULT 0,
            score_ready INTEGER NOT NULL DEFAULT 0,
            fill_history_capped INTEGER NOT NULL DEFAULT 0,
            history_complete INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_wallet_profit_metrics_ready
            ON wallet_profit_metrics(score_ready, observed_at_utc);
        CREATE TABLE IF NOT EXISTS wallet_profit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            metrics_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_wallet_profit_history_address
            ON wallet_profit_history(address, observed_at_utc DESC);
        """
    )

    existing_columns = {
        str(row[1])
        for row in con.execute("PRAGMA table_info(wallet_profit_metrics)").fetchall()
    }
    migrated = False
    if "fill_history_capped" not in existing_columns:
        con.execute(
            "ALTER TABLE wallet_profit_metrics "
            "ADD COLUMN fill_history_capped INTEGER NOT NULL DEFAULT 0"
        )
        migrated = True
    if "history_complete" not in existing_columns:
        con.execute(
            "ALTER TABLE wallet_profit_metrics "
            "ADD COLUMN history_complete INTEGER NOT NULL DEFAULT 0"
        )
        migrated = True

    if migrated:
        # The old worker stopped at four 2,000-fill pages. Rows below 8,000
        # exhausted pagination and are complete. Exact 8,000 rows must be
        # rescanned using the official 10,000-fill maximum.
        con.execute(
            """
            UPDATE wallet_profit_metrics
            SET history_complete=CASE
                    WHEN score_ready=1 AND fill_count>0 AND fill_count<8000 THEN 1
                    ELSE 0
                END,
                fill_history_capped=CASE WHEN fill_count>=8000 THEN 1 ELSE 0 END
            """
        )
        con.execute(
            """
            UPDATE wallet_profit_metrics
            SET observed_at_utc='1970-01-01T00:00:00+00:00'
            WHERE score_ready=1 AND fill_count>=8000
            """
        )

    con.commit()
    return con

def read_live_wallets(active_publisher: Path) -> list[str]:
    path = active_publisher / "wallets.txt"
    if not path.exists():
        return []
    result: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        address = raw.strip().lower()
        if valid_wallet(address) and address not in seen:
            seen.add(address)
            result.append(address)
    return result


def choose_candidate(
    con: sqlite3.Connection,
    live_wallets: list[str],
) -> str | None:
    now = utc_now()
    live_cutoff = now - dt.timedelta(hours=LIVE_RESCAN_HOURS)
    normal_cutoff = now - dt.timedelta(hours=NORMAL_RESCAN_HOURS)

    for address in live_wallets:
        row = con.execute(
            "SELECT observed_at_utc FROM wallet_profit_metrics WHERE address=?",
            (address,),
        ).fetchone()
        observed = parse_utc(row["observed_at_utc"]) if row else None
        if observed is None or observed < live_cutoff:
            return address

    rows = con.execute(
        """
        SELECT
            w.address,
            COALESCE(SUM(CASE WHEN d.day_utc >= date('now','-13 day')
                THEN d.trade_count ELSE 0 END), 0) AS trades_14d,
            COALESCE(SUM(CASE WHEN d.day_utc >= date('now','-13 day')
                THEN d.notional_usd ELSE 0 END), 0) AS notional_14d,
            m.observed_at_utc
        FROM wallets w
        LEFT JOIN wallet_trade_daily d ON d.address=w.address
        LEFT JOIN wallet_profit_metrics m ON m.address=w.address
        WHERE length(w.address)=42
          AND lower(w.address) <> ?
        GROUP BY w.address
        HAVING trades_14d >= 20 OR w.discovery_count >= 20
        ORDER BY
            CASE WHEN m.address IS NULL THEN 0 ELSE 1 END ASC,
            COALESCE(m.observed_at_utc, '') ASC,
            trades_14d DESC,
            notional_14d DESC,
            w.discovery_count DESC
        LIMIT 500
        """,
        (ZERO_ADDRESS,),
    ).fetchall()

    for row in rows:
        address = str(row["address"] or "").lower()
        if not valid_wallet(address):
            continue
        observed = parse_utc(row["observed_at_utc"])
        if observed is None or observed < normal_cutoff:
            return address
    return None


def fetch_fills(address: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    cursor = start_ms
    for _ in range(MAX_FILL_PAGES):
        raw = post_info(
            {
                "type": "userFillsByTime",
                "user": address,
                "startTime": cursor,
                "endTime": end_ms,
                "aggregateByTime": True,
            }
        )
        rows = raw if isinstance(raw, list) else []
        if not rows:
            break
        max_time = cursor
        added = 0
        for item in rows:
            if not isinstance(item, dict):
                continue
            timestamp = safe_int(item.get("time"))
            key = (
                timestamp,
                item.get("tid"),
                item.get("coin"),
                item.get("px"),
                item.get("sz"),
                item.get("dir"),
            )
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(item)
            added += 1
            max_time = max(max_time, timestamp)
        if added == 0 or max_time <= cursor or max_time >= end_ms:
            break
        cursor = max_time + 1
        time.sleep(1.0)
    all_rows.sort(key=lambda row: safe_int(row.get("time")))
    return all_rows


def fetch_funding(address: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    raw = post_info(
        {
            "type": "userFunding",
            "user": address,
            "startTime": start_ms,
            "endTime": end_ms,
        }
    )
    return [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []


def fetch_state(address: str) -> dict[str, Any]:
    raw = post_info({"type": "clearinghouseState", "user": address})
    return raw if isinstance(raw, dict) else {}


def date_key(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp / 1000, tz=dt.timezone.utc).date().isoformat()


def week_key(timestamp: int) -> str:
    value = dt.datetime.fromtimestamp(timestamp / 1000, tz=dt.timezone.utc).date()
    year, week, _ = value.isocalendar()
    return f"{year:04d}-W{week:02d}"


def calculate_metrics(
    address: str,
    fills: list[dict[str, Any]],
    funding_rows: list[dict[str, Any]],
    state: dict[str, Any],
    requested_start_ms: int,
) -> dict[str, Any]:
    daily: dict[str, float] = {}
    weekly: dict[str, float] = {}
    fill_returns: list[float] = []
    winning_values: list[float] = []
    closed_pnl = 0.0
    fees = 0.0
    wins = 0
    losses = 0
    first_ms = 0
    last_ms = 0

    for fill in fills:
        timestamp = safe_int(fill.get("time"))
        if timestamp <= 0:
            continue
        first_ms = timestamp if first_ms == 0 else min(first_ms, timestamp)
        last_ms = max(last_ms, timestamp)
        pnl = safe_float(fill.get("closedPnl"))
        fee = safe_float(fill.get("fee"))
        net = pnl - fee
        closed_pnl += pnl
        fees += fee
        fill_returns.append(net)
        if net > 0:
            wins += 1
            winning_values.append(net)
        elif net < 0:
            losses += 1
        daily[date_key(timestamp)] = daily.get(date_key(timestamp), 0.0) + net
        weekly[week_key(timestamp)] = weekly.get(week_key(timestamp), 0.0) + net

    funding = 0.0
    for row in funding_rows:
        timestamp = safe_int(row.get("time"))
        delta = row.get("delta") if isinstance(row.get("delta"), dict) else {}
        value = safe_float(delta.get("usdc"))
        funding += value
        if timestamp > 0:
            daily[date_key(timestamp)] = daily.get(date_key(timestamp), 0.0) + value
            weekly[week_key(timestamp)] = weekly.get(week_key(timestamp), 0.0) + value

    net_pnl = closed_pnl - fees + funding
    gross_profit = sum(value for value in fill_returns if value > 0)
    gross_loss = abs(sum(value for value in fill_returns if value < 0))
    largest_win_share = (
        max(winning_values) / gross_profit if gross_profit > 0 and winning_values else 1.0
    )
    worst_day_loss = abs(min([0.0, *daily.values()]))
    observed_weeks = len(weekly)
    profitable_weeks = sum(1 for value in weekly.values() if value > 0)
    profitable_week_ratio = (
        profitable_weeks / observed_weeks if observed_weeks else 0.0
    )
    decided = wins + losses
    win_rate = wins / decided if decided else 0.0
    span_days = (
        max(1.0, (last_ms - first_ms) / 86_400_000.0) if first_ms and last_ms else 0.0
    )

    summary = state.get("marginSummary") or state.get("crossMarginSummary") or {}
    account_value = safe_float(summary.get("accountValue"))
    position_value = 0.0
    open_positions = 0
    for item in state.get("assetPositions") or []:
        position = item.get("position") if isinstance(item, dict) else None
        position = position or item
        if not isinstance(position, dict):
            continue
        value = abs(safe_float(position.get("positionValue")))
        size = safe_float(position.get("szi"))
        if value > 0 and size != 0:
            position_value += value
            open_positions += 1

    fill_history_capped = 1 if len(fills) >= MAX_API_FILLS else 0
    history_complete = 1 if fills and not fill_history_capped else 0

    return {
        "address": address,
        "observed_at_utc": utc_text(),
        "lookback_days": LOOKBACK_DAYS,
        "first_fill_ms": first_ms,
        "last_fill_ms": last_ms,
        "span_days": span_days,
        "fill_count": len(fills),
        "active_days": len(daily),
        "observed_weeks": observed_weeks,
        "profitable_weeks": profitable_weeks,
        "profitable_week_ratio": profitable_week_ratio,
        "winning_fills": wins,
        "losing_fills": losses,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "closed_pnl": closed_pnl,
        "fees": fees,
        "funding": funding,
        "net_pnl": net_pnl,
        "largest_win_share": largest_win_share,
        "worst_day_loss": worst_day_loss,
        "account_value": account_value,
        "position_value": position_value,
        "open_positions": open_positions,
        "score_ready": 1 if fills else 0,
        "fill_history_capped": fill_history_capped,
        "history_complete": history_complete,
        "requested_start_ms": requested_start_ms,
        "error": "",
    }

def store_metrics(con: sqlite3.Connection, metrics: dict[str, Any]) -> None:
    columns = [
        "address", "observed_at_utc", "lookback_days", "first_fill_ms",
        "last_fill_ms", "span_days", "fill_count", "active_days",
        "observed_weeks", "profitable_weeks", "profitable_week_ratio",
        "winning_fills", "losing_fills", "win_rate", "gross_profit",
        "gross_loss", "closed_pnl", "fees", "funding", "net_pnl",
        "largest_win_share", "worst_day_loss", "account_value",
        "position_value", "open_positions", "score_ready",
        "fill_history_capped", "history_complete", "error",
    ]
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{name}=excluded.{name}" for name in columns if name != "address")
    for attempt in range(6):
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                f"""
                INSERT INTO wallet_profit_metrics({','.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(address) DO UPDATE SET {updates}
                """,
                tuple(metrics.get(name) for name in columns),
            )
            con.execute(
                """
                INSERT INTO wallet_profit_history(address, observed_at_utc, metrics_json)
                VALUES (?, ?, ?)
                """,
                (
                    metrics["address"],
                    metrics["observed_at_utc"],
                    json.dumps(metrics, separators=(",", ":"), ensure_ascii=False),
                ),
            )
            con.execute(
                """
                UPDATE wallets SET
                    last_scanned_utc=?,
                    scan_count=scan_count+1,
                    ok=?,
                    account_value=?,
                    open_positions=?,
                    position_value=?,
                    fills_count=?,
                    closed_pnl=?,
                    wins=?,
                    losses=?,
                    win_rate=?,
                    last_error=?,
                    updated_utc=?
                WHERE address=?
                """,
                (
                    metrics["observed_at_utc"],
                    1 if not metrics.get("error") else 0,
                    metrics["account_value"],
                    metrics["open_positions"],
                    metrics["position_value"],
                    metrics["fill_count"],
                    metrics["net_pnl"],
                    metrics["winning_fills"],
                    metrics["losing_fills"],
                    metrics["win_rate"],
                    metrics.get("error") or "",
                    metrics["observed_at_utc"],
                    metrics["address"],
                ),
            )
            con.commit()
            return
        except sqlite3.OperationalError as exc:
            con.rollback()
            if "locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(0.5 * (attempt + 1))

def scan_one(con: sqlite3.Connection, address: str) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - LOOKBACK_DAYS * 86_400_000
    print(f"Profit history: scanning {address[:8]}...{address[-6:]}", flush=True)
    fills = fetch_fills(address, start_ms, now_ms)
    time.sleep(1.0)
    funding = fetch_funding(address, start_ms, now_ms)
    time.sleep(1.0)
    state = fetch_state(address)
    metrics = calculate_metrics(address, fills, funding, state, start_ms)
    store_metrics(con, metrics)
    completeness = "complete" if metrics["history_complete"] else "API-capped"
    print(
        f"Profit history: {metrics['fill_count']} fills ({completeness}) | "
        f"{metrics['active_days']} active days | "
        f"{metrics['profitable_weeks']}/{metrics['observed_weeks']} profitable weeks | "
        f"net ${metrics['net_pnl']:,.2f}",
        flush=True,
    )
    return metrics

def error_metrics(address: str, error: str) -> dict[str, Any]:
    return {
        "address": address,
        "observed_at_utc": utc_text(),
        "lookback_days": LOOKBACK_DAYS,
        "first_fill_ms": 0,
        "last_fill_ms": 0,
        "span_days": 0.0,
        "fill_count": 0,
        "active_days": 0,
        "observed_weeks": 0,
        "profitable_weeks": 0,
        "profitable_week_ratio": 0.0,
        "winning_fills": 0,
        "losing_fills": 0,
        "win_rate": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "closed_pnl": 0.0,
        "fees": 0.0,
        "funding": 0.0,
        "net_pnl": 0.0,
        "largest_win_share": 1.0,
        "worst_day_loss": 0.0,
        "account_value": 0.0,
        "position_value": 0.0,
        "open_positions": 0,
        "score_ready": 0,
        "fill_history_capped": 0,
        "history_complete": 0,
        "error": error[:500],
    }

def self_test() -> None:
    address = "0x" + "1" * 40
    fills = []
    base = 1750000000000
    for index in range(120):
        fills.append(
            {
                "time": base + index * 12 * 60 * 60 * 1000,
                "closedPnl": "12" if index % 3 else "-5",
                "fee": "0.5",
            }
        )
    funding = [
        {"time": base, "delta": {"usdc": "2.5"}},
        {"time": base + 8 * 86_400_000, "delta": {"usdc": "-1.0"}},
    ]
    state = {
        "marginSummary": {"accountValue": "25000"},
        "assetPositions": [
            {"position": {"positionValue": "5000", "szi": "1"}},
        ],
    }
    metrics = calculate_metrics(address, fills, funding, state, base)
    assert metrics["fill_count"] == 120
    assert metrics["active_days"] > 20
    assert metrics["account_value"] == 25000
    assert metrics["net_pnl"] > 0
    assert metrics["history_complete"] == 1
    assert 0 <= metrics["largest_win_share"] <= 1
    print("Profit-history worker self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=r"C:\dev\hyper_wallet_tracker_saas_v1")
    parser.add_argument(
        "--active-publisher",
        default=r"C:\CopycatSnapshotPublisher\local_snapshot_publisher",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = Path(args.repo_root).expanduser().resolve()
    active = Path(args.active_publisher).expanduser().resolve()
    con = connect_db(repo)
    try:
        while True:
            live = read_live_wallets(active)
            address = choose_candidate(con, live)
            if not address:
                print("Profit history: no wallet is due; sleeping 15 minutes.", flush=True)
                if args.once:
                    return 0
                time.sleep(900)
                continue
            try:
                scan_one(con, address)
            except Exception as exc:
                print(f"Profit history warning: {exc}", flush=True)
                store_metrics(con, error_metrics(address, str(exc)))
                if "429" in str(exc):
                    time.sleep(600)
            if args.once:
                return 0
            time.sleep(max(45, args.interval_seconds))
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

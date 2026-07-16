#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import queue
import re
import signal
import sqlite3
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

INFO_URL = "https://api.hyperliquid.xyz/info"
WS_URL = "wss://api.hyperliquid.xyz/ws"
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ZERO_ADDRESS = "0x" + ("0" * 40)
SOURCE = "hyperliquid_all_market_ws_v1"


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


def valid_wallet(value: Any) -> bool:
    address = str(value or "").strip().lower()
    return bool(ADDRESS_RE.fullmatch(address)) and address != ZERO_ADDRESS


def post_info(body: dict[str, Any], timeout: int = 20) -> Any:
    request = urllib.request.Request(
        INFO_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "CopycatFreeUniverse/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def market_universe() -> tuple[list[str], list[str]]:
    dex_names = [""]
    try:
        raw_dexs = post_info({"type": "perpDexs"})
        if isinstance(raw_dexs, list):
            for item in raw_dexs:
                if isinstance(item, dict) and item.get("name"):
                    name = str(item["name"]).strip()
                    if name and name not in dex_names:
                        dex_names.append(name)
    except Exception as exc:
        print(f"Warning: perpDexs lookup failed: {exc}", flush=True)

    coins: list[str] = []
    seen: set[str] = set()
    working_dexs: list[str] = []
    for dex in dex_names:
        try:
            body: dict[str, Any] = {"type": "meta"}
            if dex:
                body["dex"] = dex
            raw = post_info(body)
            universe = raw.get("universe", []) if isinstance(raw, dict) else []
            added = 0
            for row in universe:
                if not isinstance(row, dict) or row.get("isDelisted"):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                subscription_coin = name
                if dex and ":" not in name:
                    subscription_coin = f"{dex}:{name}"
                if subscription_coin not in seen:
                    seen.add(subscription_coin)
                    coins.append(subscription_coin)
                    added += 1
            if added:
                working_dexs.append(dex or "main")
        except Exception as exc:
            print(f"Warning: meta lookup failed for dex '{dex or 'main'}': {exc}", flush=True)

    return coins, working_dexs


def connect_db(repo: Path) -> sqlite3.Connection:
    root = repo / "copycat_wallet_registry"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "copycat_wallet_registry.sqlite"
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS wallets (
            address TEXT PRIMARY KEY,
            first_seen_utc TEXT NOT NULL,
            last_seen_utc TEXT NOT NULL,
            discovery_count INTEGER NOT NULL DEFAULT 0,
            sources TEXT NOT NULL DEFAULT '',
            last_scanned_utc TEXT,
            scan_count INTEGER NOT NULL DEFAULT 0,
            ok INTEGER NOT NULL DEFAULT 0,
            qualified INTEGER NOT NULL DEFAULT 0,
            account_value REAL NOT NULL DEFAULT 0,
            withdrawable REAL NOT NULL DEFAULT 0,
            open_positions INTEGER NOT NULL DEFAULT 0,
            position_value REAL NOT NULL DEFAULT 0,
            unrealized_pnl REAL NOT NULL DEFAULT 0,
            fills_count INTEGER NOT NULL DEFAULT 0,
            active_symbols INTEGER NOT NULL DEFAULT 0,
            closed_pnl REAL NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            win_rate REAL NOT NULL DEFAULT 0,
            copycat_score REAL NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            updated_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wallet_trade_daily (
            address TEXT NOT NULL,
            day_utc TEXT NOT NULL,
            trade_count INTEGER NOT NULL DEFAULT 0,
            notional_usd REAL NOT NULL DEFAULT 0,
            first_trade_ms INTEGER NOT NULL,
            last_trade_ms INTEGER NOT NULL,
            markets_json TEXT NOT NULL DEFAULT '[]',
            updated_utc TEXT NOT NULL,
            PRIMARY KEY(address, day_utc)
        );
        CREATE INDEX IF NOT EXISTS idx_wallet_trade_daily_day
            ON wallet_trade_daily(day_utc, trade_count DESC);
        CREATE INDEX IF NOT EXISTS idx_wallet_trade_daily_address
            ON wallet_trade_daily(address, day_utc DESC);
        CREATE TABLE IF NOT EXISTS free_universe_runtime (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        );
        """
    )
    con.commit()
    return con


def day_from_ms(value: int) -> str:
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).date().isoformat()


class TradeBatch:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.trade_messages = 0
        self.wallet_observations = 0

    def add_trade(self, trade: dict[str, Any]) -> None:
        coin = str(trade.get("coin") or "").strip()
        timestamp = int(safe_float(trade.get("time")) or int(time.time() * 1000))
        price = abs(safe_float(trade.get("px")))
        size = abs(safe_float(trade.get("sz")))
        notional = price * size
        users = trade.get("users")
        if not isinstance(users, list) or len(users) < 2:
            return

        self.trade_messages += 1
        day = day_from_ms(timestamp)
        for raw_address in users[:2]:
            address = str(raw_address or "").strip().lower()
            if not valid_wallet(address):
                continue
            key = (address, day)
            row = self.rows.setdefault(
                key,
                {
                    "address": address,
                    "day_utc": day,
                    "trade_count": 0,
                    "notional_usd": 0.0,
                    "first_trade_ms": timestamp,
                    "last_trade_ms": timestamp,
                    "markets": set(),
                },
            )
            row["trade_count"] += 1
            row["notional_usd"] += notional
            row["first_trade_ms"] = min(row["first_trade_ms"], timestamp)
            row["last_trade_ms"] = max(row["last_trade_ms"], timestamp)
            if coin:
                row["markets"].add(coin)
            self.wallet_observations += 1

    def pop_all(self) -> tuple[list[dict[str, Any]], int, int]:
        values = list(self.rows.values())
        trades = self.trade_messages
        observations = self.wallet_observations
        self.rows = {}
        self.trade_messages = 0
        self.wallet_observations = 0
        return values, trades, observations


def write_batch(con: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    now = utc_text()
    for attempt in range(6):
        try:
            con.execute("BEGIN IMMEDIATE")
            for row in rows:
                markets = sorted(row["markets"])[:80]
                con.execute(
                    """
                    INSERT INTO wallets(
                        address, first_seen_utc, last_seen_utc,
                        discovery_count, sources, updated_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(address) DO UPDATE SET
                        last_seen_utc=excluded.last_seen_utc,
                        discovery_count=wallets.discovery_count + excluded.discovery_count,
                        sources=CASE
                            WHEN instr(wallets.sources, ?) > 0 THEN wallets.sources
                            WHEN wallets.sources='' THEN ?
                            ELSE wallets.sources || ',' || ?
                        END,
                        updated_utc=excluded.updated_utc
                    """,
                    (
                        row["address"],
                        now,
                        now,
                        int(row["trade_count"]),
                        SOURCE,
                        now,
                        SOURCE,
                        SOURCE,
                        SOURCE,
                    ),
                )
                existing = con.execute(
                    """
                    SELECT markets_json FROM wallet_trade_daily
                    WHERE address=? AND day_utc=?
                    """,
                    (row["address"], row["day_utc"]),
                ).fetchone()
                merged_markets = set(markets)
                if existing:
                    try:
                        merged_markets.update(json.loads(existing["markets_json"] or "[]"))
                    except Exception:
                        pass
                con.execute(
                    """
                    INSERT INTO wallet_trade_daily(
                        address, day_utc, trade_count, notional_usd,
                        first_trade_ms, last_trade_ms, markets_json, updated_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(address, day_utc) DO UPDATE SET
                        trade_count=wallet_trade_daily.trade_count + excluded.trade_count,
                        notional_usd=wallet_trade_daily.notional_usd + excluded.notional_usd,
                        first_trade_ms=min(wallet_trade_daily.first_trade_ms, excluded.first_trade_ms),
                        last_trade_ms=max(wallet_trade_daily.last_trade_ms, excluded.last_trade_ms),
                        markets_json=excluded.markets_json,
                        updated_utc=excluded.updated_utc
                    """,
                    (
                        row["address"],
                        row["day_utc"],
                        int(row["trade_count"]),
                        float(row["notional_usd"]),
                        int(row["first_trade_ms"]),
                        int(row["last_trade_ms"]),
                        json.dumps(sorted(merged_markets)[:100], separators=(",", ":")),
                        now,
                    ),
                )
            con.commit()
            return
        except sqlite3.OperationalError as exc:
            con.rollback()
            if "locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(0.5 * (attempt + 1))


def status_payload(
    con: sqlite3.Connection,
    markets: list[str],
    dexs: list[str],
    trades_seen: int,
    observations: int,
    started_at: str,
    connections: int,
    errors: list[str],
) -> dict[str, Any]:
    wallet_count = int(con.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
    seven_day = int(
        con.execute(
            """
            SELECT COUNT(DISTINCT address)
            FROM wallet_trade_daily
            WHERE day_utc >= date('now', '-6 day')
            """
        ).fetchone()[0]
    )
    return {
        "status": "ok" if markets and connections else "degraded",
        "source": SOURCE,
        "started_at_utc": started_at,
        "updated_at_utc": utc_text(),
        "updated_at_ms": int(time.time() * 1000),
        "markets_subscribed": len(markets),
        "dexs_subscribed": dexs,
        "connections": connections,
        "trade_messages_seen": trades_seen,
        "wallet_observations_seen": observations,
        "unique_wallets_indexed": wallet_count,
        "wallets_active_7d": seven_day,
        "errors": errors[-8:],
        "note": "Public all-market trades stream. Wallets are discovered from both sides of each trade.",
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def websocket_worker(
    coins: list[str],
    output: queue.Queue[dict[str, Any]],
    stop: threading.Event,
    errors: list[str],
    index: int,
) -> None:
    try:
        import websocket  # type: ignore
    except Exception as exc:
        errors.append(f"websocket-client missing: {exc}")
        stop.set()
        return

    while not stop.is_set():
        ws = None
        try:
            ws = websocket.create_connection(WS_URL, timeout=30, enable_multithread=True)
            for coin in coins:
                ws.send(
                    json.dumps(
                        {
                            "method": "subscribe",
                            "subscription": {"type": "trades", "coin": coin},
                        },
                        separators=(",", ":"),
                    )
                )
                time.sleep(0.002)
            print(f"Discovery connection {index}: subscribed to {len(coins)} markets", flush=True)

            while not stop.is_set():
                try:
                    raw = ws.recv()
                except Exception as exc:
                    if "timed out" in str(exc).lower():
                        ws.send('{"method":"ping"}')
                        continue
                    raise
                if not raw:
                    continue
                try:
                    message = json.loads(raw)
                except Exception:
                    continue
                if message.get("channel") != "trades":
                    continue
                data = message.get("data")
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            output.put(item)
        except Exception as exc:
            errors.append(f"connection {index}: {exc}")
            print(f"Discovery connection {index} reconnecting: {exc}", flush=True)
            time.sleep(5)
        finally:
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass


def run(repo: Path, active_publisher: Path, run_seconds: int = 0) -> int:
    markets, dexs = market_universe()
    if not markets:
        raise RuntimeError("Hyperliquid returned no active perpetual markets.")

    chunks = [markets[i : i + 400] for i in range(0, len(markets), 400)]
    if len(chunks) > 9:
        chunks = chunks[:9]
        markets = [coin for chunk in chunks for coin in chunk]
        print("Warning: market list exceeded safe WebSocket connection limit; first 3600 used.", flush=True)

    con = connect_db(repo)
    output: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200000)
    stop = threading.Event()
    errors: list[str] = []
    started_at = utc_text()
    threads: list[threading.Thread] = []

    def request_stop(*_: Any) -> None:
        stop.set()

    try:
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)
    except Exception:
        pass

    for index, chunk in enumerate(chunks, start=1):
        thread = threading.Thread(
            target=websocket_worker,
            args=(chunk, output, stop, errors, index),
            daemon=True,
        )
        thread.start()
        threads.append(thread)

    status_paths = [
        repo / "copycat_wallet_registry" / "free_universe_status.json",
        active_publisher / "scanner_state" / "free_universe_status.json",
    ]
    batch = TradeBatch()
    trades_seen = 0
    observations = 0
    last_flush = time.monotonic()
    deadline = time.monotonic() + run_seconds if run_seconds > 0 else None

    try:
        while not stop.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                stop.set()
                break
            try:
                trade = output.get(timeout=1)
                batch.add_trade(trade)
            except queue.Empty:
                pass

            if time.monotonic() - last_flush >= 5 or len(batch.rows) >= 5000:
                rows, trades, seen = batch.pop_all()
                write_batch(con, rows)
                trades_seen += trades
                observations += seen
                payload = status_payload(
                    con,
                    markets,
                    dexs,
                    trades_seen,
                    observations,
                    started_at,
                    sum(1 for thread in threads if thread.is_alive()),
                    errors,
                )
                for path in status_paths:
                    try:
                        atomic_json(path, payload)
                    except Exception:
                        pass
                print(
                    f"Discovery: {payload['unique_wallets_indexed']:,} wallets | "
                    f"{payload['wallets_active_7d']:,} active 7d | "
                    f"{trades_seen:,} trades this run",
                    flush=True,
                )
                last_flush = time.monotonic()
    finally:
        rows, trades, seen = batch.pop_all()
        write_batch(con, rows)
        trades_seen += trades
        observations += seen
        payload = status_payload(
            con,
            markets,
            dexs,
            trades_seen,
            observations,
            started_at,
            sum(1 for thread in threads if thread.is_alive()),
            errors,
        )
        for path in status_paths:
            try:
                atomic_json(path, payload)
            except Exception:
                pass
        con.close()

    return 0


def self_test() -> None:
    batch = TradeBatch()
    batch.add_trade(
        {
            "coin": "BTC",
            "px": "100",
            "sz": "2",
            "time": 1760000000000,
            "tid": 1,
            "users": [
                "0x" + "1" * 40,
                "0x" + "2" * 40,
            ],
        }
    )
    rows, trades, observations = batch.pop_all()
    assert trades == 1
    assert observations == 2
    assert len(rows) == 2
    assert rows[0]["notional_usd"] == 200
    assert valid_wallet(rows[0]["address"])
    assert not valid_wallet(ZERO_ADDRESS)
    print("All-market discovery self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=False, default=r"C:\dev\hyper_wallet_tracker_saas_v1")
    parser.add_argument(
        "--active-publisher",
        default=r"C:\CopycatSnapshotPublisher\local_snapshot_publisher",
    )
    parser.add_argument("--run-seconds", type=int, default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    return run(
        Path(args.repo_root).expanduser().resolve(),
        Path(args.active_publisher).expanduser().resolve(),
        max(0, args.run_seconds),
    )


if __name__ == "__main__":
    raise SystemExit(main())

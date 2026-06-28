#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request, error

API_URL = "https://api.hyperliquid.xyz/info"
ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
BUILTIN_BLOCKED_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0xffffffffffffffffffffffffffffffffffffffff",
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "0x1111111111111111111111111111111111111111",
    "0x2222222222222222222222222222222222222222",
    "0x3333333333333333333333333333333333333333",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
}

def looks_like_non_trader_address(address: str) -> bool:
    address = (address or "").strip().lower()
    if not ADDRESS_RE.fullmatch(address): return True
    body = address[2:]
    if address in BUILTIN_BLOCKED_ADDRESSES: return True
    if len(set(body)) == 1: return True
    if re.fullmatch(r"0x200000000000000000000000000000000000[0-9a-f]{4}", address): return True
    return False


TEXT_EXTENSIONS = {
    ".txt", ".csv", ".json", ".jsonl", ".md", ".py", ".ts", ".tsx",
    ".js", ".jsx", ".env", ".example", ".yaml", ".yml", ".log"
}

EXCLUDE_PARTS = {
    ".git", "node_modules", ".next", "_copycat_patch_backups",
    "copycat_daily_scout_out", "copycat_daily_scout_out_v2",
    "copycat_wallet_registry", "__pycache__", ".venv", "venv"
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def json_post(body: dict[str, Any], timeout: int = 30, retries: int = 3) -> Any:
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CopycatWalletRegistry/2.1"
    }

    last_error: Exception | None = None
    for attempt in range(retries):
        req = request.Request(API_URL, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except error.HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                sleep_for = 60 + attempt * 60
                print(f"429 rate limit seen. Sleeping {sleep_for}s before retry...")
                time.sleep(sleep_for)
                continue
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = str(exc)
            raise RuntimeError(f"HTTP {exc.code}: {raw[:500]}") from exc
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                sleep_for = 10 + attempt * 10
                print(f"Temporary API error: {exc}. Sleeping {sleep_for}s before retry...")
                time.sleep(sleep_for)
                continue
            break

    raise RuntimeError(f"API request failed after {retries} attempt(s): {last_error}")


def normalize_address(address: str) -> str | None:
    address = address.strip().lower()
    if ADDRESS_RE.fullmatch(address):
        return address
    return None


def extract_addresses_from_text(text: str) -> set[str]:
    addresses = {m.group(0).lower() for m in ADDRESS_RE.finditer(text)}
    return {a for a in addresses if not looks_like_non_trader_address(a)}


def walk_json_for_addresses(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for value in obj.values():
            found |= walk_json_for_addresses(value)
    elif isinstance(obj, list):
        for item in obj:
            found |= walk_json_for_addresses(item)
    elif isinstance(obj, str):
        found |= extract_addresses_from_text(obj)
    return found


def output_root(repo: Path) -> Path:
    return repo / "copycat_wallet_registry"


def db_path(repo: Path) -> Path:
    return output_root(repo) / "copycat_wallet_registry.sqlite"


def connect_db(repo: Path) -> sqlite3.Connection:
    out = output_root(repo)
    out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path(repo))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
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

        CREATE TABLE IF NOT EXISTS discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            source TEXT NOT NULL,
            discovered_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            scanned_utc TEXT NOT NULL,
            ok INTEGER NOT NULL DEFAULT 0,
            qualified INTEGER NOT NULL DEFAULT 0,
            account_value REAL NOT NULL DEFAULT 0,
            closed_pnl REAL NOT NULL DEFAULT 0,
            fills_count INTEGER NOT NULL DEFAULT 0,
            copycat_score REAL NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_wallets_score ON wallets(copycat_score DESC);
        CREATE INDEX IF NOT EXISTS idx_wallets_closed_pnl ON wallets(closed_pnl DESC);
        CREATE INDEX IF NOT EXISTS idx_wallets_last_scanned ON wallets(last_scanned_utc);
        CREATE INDEX IF NOT EXISTS idx_wallets_qualified ON wallets(qualified);
        CREATE INDEX IF NOT EXISTS idx_discoveries_address ON discoveries(address);
        """
    )
    conn.commit()


def merge_source(existing: str, new_source: str) -> str:
    parts = [p for p in existing.split(";") if p]
    if new_source not in parts:
        parts.append(new_source)
    return ";".join(parts[:20])


def add_wallet(conn: sqlite3.Connection, address: str, source: str, now: str) -> bool:
    address = (address or "").strip().lower()
    if looks_like_non_trader_address(address):
        return False
    row = conn.execute("SELECT address, sources FROM wallets WHERE address = ?", (address,)).fetchone()
    if row:
        sources = merge_source(row["sources"], source)
        conn.execute(
            """
            UPDATE wallets
            SET last_seen_utc = ?, discovery_count = discovery_count + 1, sources = ?, updated_utc = ?
            WHERE address = ?
            """,
            (now, sources, now, address),
        )
        is_new = False
    else:
        conn.execute(
            """
            INSERT INTO wallets(address, first_seen_utc, last_seen_utc, discovery_count, sources, updated_utc)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (address, now, now, source, now),
        )
        is_new = True

    conn.execute(
        "INSERT INTO discoveries(address, source, discovered_utc) VALUES (?, ?, ?)",
        (address, source, now),
    )
    return is_new


def good_text_file(path: Path, max_file_mb: int) -> bool:
    parts = {p.lower() for p in path.parts}
    if any(part in parts for part in EXCLUDE_PARTS):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        return path.is_file() and path.stat().st_size <= max_file_mb * 1024 * 1024
    except OSError:
        return False


def discover_from_file(conn: sqlite3.Connection, path: Path, source_prefix: str, max_file_mb: int) -> tuple[int, int]:
    if not path.exists() or not path.is_file() or not good_text_file(path, max_file_mb=max_file_mb):
        return (0, 0)

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return (0, 0)

    addresses = extract_addresses_from_text(text)
    now = utc_stamp()
    new_count = 0
    for address in addresses:
        if add_wallet(conn, address, f"{source_prefix}:{path}", now):
            new_count += 1
    return (len(addresses), new_count)


def discover_from_path(conn: sqlite3.Connection, path: Path, source_prefix: str, max_file_mb: int) -> tuple[int, int, int]:
    if not path.exists():
        return (0, 0, 0)

    files = [path] if path.is_file() else [p for p in path.rglob("*") if good_text_file(p, max_file_mb=max_file_mb)]
    seen = 0
    new = 0
    touched = 0

    for file_path in files:
        file_seen, file_new = discover_from_file(conn, file_path, source_prefix, max_file_mb=max_file_mb)
        if file_seen:
            touched += 1
            seen += file_seen
            new += file_new

    conn.commit()
    return (seen, new, touched)


def discover_from_vault_summaries(conn: sqlite3.Connection) -> tuple[int, int]:
    try:
        data = json_post({"type": "vaultSummaries"}, timeout=30, retries=2)
    except Exception as exc:
        print(f"Vault discovery skipped: {exc}")
        return (0, 0)

    addresses = walk_json_for_addresses(data)
    now = utc_stamp()
    new_count = 0
    for address in addresses:
        if add_wallet(conn, address, "hyperliquid:vaultSummaries", now):
            new_count += 1
    conn.commit()
    return (len(addresses), new_count)


def default_discovery_paths(repo: Path) -> list[Path]:
    paths = [
        repo,
        repo / "scripts" / "daily_wallet_scout_v2",
        repo / "copycat_daily_scout_out_v2",
        Path(r"C:\CopycatSnapshotPublisher\local_snapshot_publisher"),
    ]
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        old = Path(userprofile) / "OneDrive" / "Desktop" / "hyper_wallet_tracker_saas_v1_OLD_DO_NOT_USE"
        if old.exists():
            paths.append(old)
    return paths


def run_discover(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect_db(repo)

    total_seen = 0
    total_new = 0
    total_files = 0

    print("Copycat Wallet Registry: discovery")
    print(f"Database: {db_path(repo)}")

    paths = default_discovery_paths(repo)
    for extra in args.scan_path or []:
        paths.append(Path(extra).expanduser())

    for p in paths:
        print(f"Discovering from: {p}")
        seen, new, files = discover_from_path(conn, p, "file", max_file_mb=args.max_file_mb)
        total_seen += seen
        total_new += new
        total_files += files

    if not args.skip_vault_candidates:
        print("Discovering from Hyperliquid vault summaries...")
        seen, new = discover_from_vault_summaries(conn)
        total_seen += seen
        total_new += new

    wallet_count = conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"]
    summary = {
        "mode": "discover",
        "wallets_total_in_registry": wallet_count,
        "addresses_seen_this_run": total_seen,
        "new_wallets_added_this_run": total_new,
        "files_with_addresses": total_files,
        "database": str(db_path(repo)),
        "time_utc": utc_stamp(),
    }

    write_summary(repo, summary, "discover_summary.json")
    print(json.dumps(summary, indent=2))
    return 0


def choose_due_wallets(conn: sqlite3.Connection, limit: int, rescan_after_hours: int) -> list[str]:
    cutoff = (utc_now() - dt.timedelta(hours=rescan_after_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        """
        SELECT address
        FROM wallets
        WHERE last_scanned_utc IS NULL OR last_scanned_utc < ?
        ORDER BY
          CASE WHEN last_scanned_utc IS NULL THEN 0 ELSE 1 END ASC,
          last_scanned_utc ASC,
          discovery_count DESC,
          first_seen_utc ASC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [r["address"] for r in rows]


def position_number(position: dict[str, Any], key: str) -> float:
    return safe_float(position.get(key, 0))


def score_wallet(address: str, min_account_value: float, min_fills: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "address": address,
        "ok": 0,
        "qualified": 0,
        "account_value": 0.0,
        "withdrawable": 0.0,
        "open_positions": 0,
        "position_value": 0.0,
        "unrealized_pnl": 0.0,
        "fills_count": 0,
        "active_symbols": 0,
        "closed_pnl": 0.0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "copycat_score": 0.0,
        "last_error": "",
    }

    try:
        clearing = json_post({"type": "clearinghouseState", "user": address}, timeout=30, retries=3)
        # Essential ranking signal only: recent/user fills summary, not permanent raw fill storage.
        fills = json_post({"type": "userFills", "user": address}, timeout=30, retries=3)
    except Exception as exc:
        row["last_error"] = str(exc)[:1000]
        return row

    if not isinstance(clearing, dict):
        row["last_error"] = "clearinghouseState returned non-object response"
        return row

    margin = clearing.get("marginSummary") or clearing.get("crossMarginSummary") or {}
    row["account_value"] = round(safe_float(margin.get("accountValue")), 8)
    row["withdrawable"] = round(safe_float(clearing.get("withdrawable")), 8)

    positions = clearing.get("assetPositions") or []
    open_positions = []
    position_value = 0.0
    unrealized = 0.0

    if isinstance(positions, list):
        for item in positions:
            pos = item.get("position", item) if isinstance(item, dict) else {}
            if not isinstance(pos, dict):
                continue
            szi = position_number(pos, "szi")
            if abs(szi) <= 0:
                continue
            open_positions.append(pos)
            position_value += abs(position_number(pos, "positionValue"))
            unrealized += position_number(pos, "unrealizedPnl")

    row["open_positions"] = len(open_positions)
    row["position_value"] = round(position_value, 8)
    row["unrealized_pnl"] = round(unrealized, 8)

    if not isinstance(fills, list):
        fills = []

    symbols: set[str] = set()
    closed_values: list[float] = []
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        coin = fill.get("coin")
        if coin:
            symbols.add(str(coin))
        if "closedPnl" in fill:
            closed_values.append(safe_float(fill.get("closedPnl")))

    wins = sum(1 for x in closed_values if x > 0)
    losses = sum(1 for x in closed_values if x < 0)

    row["fills_count"] = len(fills)
    row["active_symbols"] = len(symbols)
    row["closed_pnl"] = round(sum(closed_values), 8)
    row["wins"] = wins
    row["losses"] = losses
    row["win_rate"] = round(wins / (wins + losses), 8) if (wins + losses) else 0.0

    # Essential summary ranking only. This is a Copycat score, not an all-time audited profit claim.
    account_score = min(math.log10(max(row["account_value"], 0) + 1) * 15, 75)
    pnl_score = max(min(row["closed_pnl"] / 100, 70), -70)
    unrealized_score = max(min(row["unrealized_pnl"] / 100, 30), -30)
    activity_score = min(row["fills_count"], 300) * 0.15
    diversity_score = min(row["active_symbols"], 25) * 1.0
    open_position_score = min(row["open_positions"], 12) * 1.5
    win_rate_score = (row["win_rate"] - 0.5) * 25 if (wins + losses) >= 5 else 0

    score = account_score + pnl_score + unrealized_score + activity_score + diversity_score + open_position_score + win_rate_score

    if row["account_value"] < min_account_value:
        score -= 50
    if row["fills_count"] < min_fills:
        score -= 30

    row["copycat_score"] = round(score, 8)
    row["qualified"] = int(row["account_value"] >= min_account_value and row["fills_count"] >= min_fills)
    row["ok"] = 1
    return row


def update_wallet_score(conn: sqlite3.Connection, metrics: dict[str, Any], scanned_utc: str) -> None:
    conn.execute(
        """
        UPDATE wallets
        SET
          last_scanned_utc = ?,
          scan_count = scan_count + 1,
          ok = ?,
          qualified = ?,
          account_value = ?,
          withdrawable = ?,
          open_positions = ?,
          position_value = ?,
          unrealized_pnl = ?,
          fills_count = ?,
          active_symbols = ?,
          closed_pnl = ?,
          wins = ?,
          losses = ?,
          win_rate = ?,
          copycat_score = ?,
          last_error = ?,
          updated_utc = ?
        WHERE address = ?
        """,
        (
            scanned_utc,
            metrics["ok"],
            metrics["qualified"],
            metrics["account_value"],
            metrics["withdrawable"],
            metrics["open_positions"],
            metrics["position_value"],
            metrics["unrealized_pnl"],
            metrics["fills_count"],
            metrics["active_symbols"],
            metrics["closed_pnl"],
            metrics["wins"],
            metrics["losses"],
            metrics["win_rate"],
            metrics["copycat_score"],
            metrics["last_error"],
            scanned_utc,
            metrics["address"],
        ),
    )
    conn.execute(
        """
        INSERT INTO scan_history(
          address, scanned_utc, ok, qualified, account_value, closed_pnl,
          fills_count, copycat_score, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metrics["address"],
            scanned_utc,
            metrics["ok"],
            metrics["qualified"],
            metrics["account_value"],
            metrics["closed_pnl"],
            metrics["fills_count"],
            metrics["copycat_score"],
            metrics["last_error"],
        ),
    )


def run_score(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect_db(repo)

    # Discovery first, so this run can grow the registry before choosing due wallets.
    if not args.skip_discovery_first:
        discover_args = argparse.Namespace(
            repo_root=str(repo),
            scan_path=[],
            max_file_mb=args.max_file_mb,
            skip_vault_candidates=args.skip_vault_candidates,
        )
        run_discover(discover_args)

    due = choose_due_wallets(conn, limit=args.max_scan, rescan_after_hours=args.rescan_after_hours)
    print("")
    print("Copycat Wallet Registry: scoring")
    print(f"Database: {db_path(repo)}")
    print(f"Wallets due this run: {len(due)} / max {args.max_scan}")

    started = time.time()
    scanned = 0
    ok = 0
    qualified = 0
    errors = 0

    for i, address in enumerate(due, start=1):
        print(f"[{i}/{len(due)}] Scoring {address}")
        scanned_utc = utc_stamp()
        metrics = score_wallet(address, min_account_value=args.min_account_value, min_fills=args.min_fills)
        update_wallet_score(conn, metrics, scanned_utc)
        conn.commit()

        scanned += 1
        ok += int(metrics["ok"] == 1)
        qualified += int(metrics["qualified"] == 1)
        errors += int(metrics["ok"] != 1)

        if args.api_sleep > 0 and i < len(due):
            time.sleep(args.api_sleep)

    export_registry(repo, conn, top_n=args.top_n)

    wallet_count = conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"]
    scanned_count = conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"]
    total_qualified = conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE qualified = 1").fetchone()["n"]

    summary = {
        "mode": "score",
        "wallets_total_in_registry": wallet_count,
        "wallets_scanned_ever": scanned_count,
        "wallets_scanned_this_run": scanned,
        "ok_this_run": ok,
        "qualified_this_run": qualified,
        "errors_this_run": errors,
        "qualified_total": total_qualified,
        "max_scan": args.max_scan,
        "api_sleep_seconds": args.api_sleep,
        "elapsed_seconds": round(time.time() - started, 2),
        "database": str(db_path(repo)),
        "time_utc": utc_stamp(),
    }
    write_summary(repo, summary, "score_summary.json")
    print(json.dumps(summary, indent=2))
    return 0


def rows_to_csv(path: Path, rows: list[sqlite3.Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(dict(row))


def export_registry(repo: Path, conn: sqlite3.Connection, top_n: int = 50) -> dict[str, Any]:
    exports = output_root(repo) / "exports"
    exports.mkdir(parents=True, exist_ok=True)

    all_rows = conn.execute(
        """
        SELECT address, first_seen_utc, last_seen_utc, discovery_count, sources,
               last_scanned_utc, scan_count, ok, qualified, account_value, withdrawable,
               open_positions, position_value, unrealized_pnl, fills_count, active_symbols,
               closed_pnl, wins, losses, win_rate, copycat_score, last_error, updated_utc
        FROM wallets
        ORDER BY copycat_score DESC, closed_pnl DESC, account_value DESC
        """
    ).fetchall()
    rows_to_csv(exports / "wallet_registry_export.csv", all_rows)

    top_score = conn.execute(
        """
        SELECT *
        FROM wallets
        WHERE qualified = 1
        ORDER BY copycat_score DESC, closed_pnl DESC, account_value DESC
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()
    rows_to_csv(exports / "top50_by_copycat_score.csv", top_score)
    (exports / "recommended_wallets_top50.txt").write_text(
        "\n".join(row["address"] for row in top_score) + ("\n" if top_score else ""),
        encoding="utf-8",
    )

    top_pnl = conn.execute(
        """
        SELECT *
        FROM wallets
        WHERE qualified = 1
        ORDER BY closed_pnl DESC, copycat_score DESC, account_value DESC
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()
    rows_to_csv(exports / "top50_by_closed_pnl.csv", top_pnl)
    (exports / "top50_by_closed_pnl.txt").write_text(
        "\n".join(row["address"] for row in top_pnl) + ("\n" if top_pnl else ""),
        encoding="utf-8",
    )

    summary = {
        "wallets_total_in_registry": conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"],
        "wallets_scanned_ever": conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"],
        "wallets_qualified": conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE qualified = 1").fetchone()["n"],
        "recommended_wallets": len(top_score),
        "exports_folder": str(exports),
        "time_utc": utc_stamp(),
        "scope_label": f"Top {len(top_score)} Copycat-ranked wallets from local registry",
    }
    write_summary(repo, summary, "export_summary.json")
    (exports / "export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def write_summary(repo: Path, summary: dict[str, Any], name: str) -> None:
    out = output_root(repo)
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_export(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect_db(repo)
    summary = export_registry(repo, conn, top_n=args.top_n)
    print(json.dumps(summary, indent=2))
    return 0


def run_status(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect_db(repo)
    summary = {
        "database": str(db_path(repo)),
        "wallets_total": conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"],
        "wallets_scanned_ever": conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"],
        "wallets_qualified": conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE qualified = 1").fetchone()["n"],
        "unscanned_wallets": conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NULL").fetchone()["n"],
        "last_scan_utc": conn.execute("SELECT MAX(last_scanned_utc) AS v FROM wallets").fetchone()["v"],
        "top_copycat_score": conn.execute("SELECT MAX(copycat_score) AS v FROM wallets").fetchone()["v"],
        "top_closed_pnl": conn.execute("SELECT MAX(closed_pnl) AS v FROM wallets").fetchone()["v"],
    }
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Copycat lightweight wallet registry v2.1")
    parser.add_argument("--repo-root", default=".", help="Copycat repo root")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="Discover wallet addresses and add them to the registry")
    d.add_argument("--scan-path", action="append", default=[], help="Extra path to scan for wallet addresses")
    d.add_argument("--max-file-mb", type=int, default=5)
    d.add_argument("--skip-vault-candidates", action="store_true")
    d.set_defaults(func=run_discover)

    s = sub.add_parser("score", help="Score due wallets and update registry")
    s.add_argument("--max-scan", type=int, default=500)
    s.add_argument("--top-n", type=int, default=50)
    s.add_argument("--api-sleep", type=float, default=2.5)
    s.add_argument("--min-account-value", type=float, default=25.0)
    s.add_argument("--min-fills", type=int, default=1)
    s.add_argument("--rescan-after-hours", type=int, default=168)
    s.add_argument("--max-file-mb", type=int, default=5)
    s.add_argument("--skip-discovery-first", action="store_true")
    s.add_argument("--skip-vault-candidates", action="store_true")
    s.set_defaults(func=run_score)

    e = sub.add_parser("export", help="Export registry CSVs and top 50 text files")
    e.add_argument("--top-n", type=int, default=50)
    e.set_defaults(func=run_export)

    st = sub.add_parser("status", help="Show registry status")
    st.set_defaults(func=run_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request, error

API_URL = "https://api.hyperliquid.xyz/info"
ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

TEXT_EXTENSIONS = {
    ".txt", ".csv", ".json", ".jsonl", ".md", ".py", ".ts", ".tsx",
    ".js", ".jsx", ".env", ".example", ".yaml", ".yml"
}

EXCLUDE_PARTS = {
    ".git", "node_modules", ".next", "_copycat_patch_backups",
    "copycat_daily_scout_out", "copycat_daily_scout_out_v2",
    "__pycache__", ".venv", "venv"
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def json_post(body: dict[str, Any], timeout: int = 30, retries: int = 3) -> Any:
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "CopycatDailyScoutV2/1.0"
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
                sleep_for = 30 + (attempt * 30)
                print(f"Rate limited by API. Sleeping {sleep_for}s before retry...")
                time.sleep(sleep_for)
                continue
            try:
                raw = exc.read().decode("utf-8", errors="replace")
            except Exception:
                raw = str(exc)
            raise RuntimeError(f"HTTP {exc.code}: {raw[:500]}") from exc
        except Exception as exc:
            last_error = exc
            sleep_for = 5 + attempt * 5
            if attempt < retries - 1:
                print(f"Temporary API error: {exc}. Sleeping {sleep_for}s before retry...")
                time.sleep(sleep_for)
                continue
            break

    raise RuntimeError(f"API request failed after {retries} attempt(s): {last_error}")


def is_good_path(path: Path, max_file_mb: int) -> bool:
    parts = {p.lower() for p in path.parts}
    if any(part in parts for part in EXCLUDE_PARTS):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    try:
        return path.is_file() and path.stat().st_size <= max_file_mb * 1024 * 1024
    except OSError:
        return False


def extract_addresses_from_text(text: str) -> list[str]:
    return [m.group(0).lower() for m in ADDRESS_RE.finditer(text)]


def walk_json_for_addresses(obj: Any) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            found.extend(walk_json_for_addresses(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(walk_json_for_addresses(item))
    elif isinstance(obj, str):
        found.extend(extract_addresses_from_text(obj))
    return found


def add_candidate(candidates: dict[str, set[str]], address: str, source: str) -> None:
    address = address.strip().lower()
    if ADDRESS_RE.fullmatch(address):
        candidates.setdefault(address, set()).add(source)


def read_candidate_file(path: Path, candidates: dict[str, set[str]], source_name: str) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    for address in extract_addresses_from_text(text):
        add_candidate(candidates, address, source_name)


def scan_path_for_candidates(path: Path, candidates: dict[str, set[str]], max_file_mb: int) -> None:
    if not path.exists():
        return
    if path.is_file():
        files = [path]
    else:
        files = []
        for p in path.rglob("*"):
            if is_good_path(p, max_file_mb=max_file_mb):
                files.append(p)

    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(p)
        for address in extract_addresses_from_text(text):
            add_candidate(candidates, address, f"file:{rel}")


def fetch_vault_candidates(candidates: dict[str, set[str]]) -> int:
    try:
        data = json_post({"type": "vaultSummaries"}, timeout=30, retries=2)
    except Exception as exc:
        print(f"Vault candidate fetch skipped: {exc}")
        return 0

    before = len(candidates)
    for address in walk_json_for_addresses(data):
        add_candidate(candidates, address, "hyperliquid:vaultSummaries")
    return len(candidates) - before


def position_number(position: dict[str, Any], key: str) -> float:
    return safe_float(position.get(key, 0))


def score_wallet(address: str, min_account_value: float, min_fills: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "address": address,
        "ok": False,
        "qualified": False,
        "score": 0.0,
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
        "error": "",
    }

    try:
        clearing = json_post({"type": "clearinghouseState", "user": address}, timeout=30, retries=3)
        fills = json_post({"type": "userFills", "user": address}, timeout=30, retries=3)
    except Exception as exc:
        row["error"] = str(exc)[:500]
        return row

    if not isinstance(clearing, dict):
        row["error"] = "clearinghouseState returned non-object response"
        return row

    margin = clearing.get("marginSummary") or clearing.get("crossMarginSummary") or {}
    row["account_value"] = safe_float(margin.get("accountValue"))
    row["withdrawable"] = safe_float(clearing.get("withdrawable"))

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
    row["position_value"] = round(position_value, 6)
    row["unrealized_pnl"] = round(unrealized, 6)

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
        closed = safe_float(fill.get("closedPnl"), None)
        if closed is not None:
            closed_values.append(closed)

    row["fills_count"] = len(fills)
    row["active_symbols"] = len(symbols)
    row["closed_pnl"] = round(sum(closed_values), 6)
    row["wins"] = sum(1 for x in closed_values if x > 0)
    row["losses"] = sum(1 for x in closed_values if x < 0)
    if row["wins"] + row["losses"] > 0:
        row["win_rate"] = round(row["wins"] / (row["wins"] + row["losses"]), 6)

    # Simple transparent score. This is a ranking signal, not a financial claim.
    account_score = min(math.log10(max(row["account_value"], 0) + 1) * 18, 80)
    pnl_score = max(min(row["closed_pnl"] / 100, 40), -40)
    unrealized_score = max(min(row["unrealized_pnl"] / 100, 25), -25)
    activity_score = min(row["fills_count"], 250) * 0.18
    diversity_score = min(row["active_symbols"], 20) * 1.2
    open_position_score = min(row["open_positions"], 10) * 2.0
    win_rate_score = (row["win_rate"] - 0.5) * 20 if (row["wins"] + row["losses"]) >= 5 else 0

    score = account_score + pnl_score + unrealized_score + activity_score + diversity_score + open_position_score + win_rate_score

    if row["account_value"] < min_account_value:
        score -= 50
    if row["fills_count"] < min_fills:
        score -= 30

    row["score"] = round(score, 6)
    row["qualified"] = bool(row["account_value"] >= min_account_value and row["fills_count"] >= min_fills)
    row["ok"] = True
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "address", "ok", "qualified", "score", "account_value", "withdrawable",
        "open_positions", "position_value", "unrealized_pnl", "fills_count",
        "active_symbols", "closed_pnl", "wins", "losses", "win_rate", "sources", "error"
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def copy_latest_outputs(run_dir: Path, out_root: Path) -> None:
    latest = out_root / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in [
        "scan_summary.json",
        "wallet_scorecards.csv",
        "recommended_wallets_top50.txt",
        "candidate_wallets_scanned.txt",
        "README_NEXT_STEPS.txt",
    ]:
        src = run_dir / name
        if src.exists():
            (latest / name).write_text(src.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Copycat Daily Scout v2 - safe Hyperliquid wallet scanner")
    parser.add_argument("--repo-root", default=".", help="Copycat repo root")
    parser.add_argument("--max-scan", type=int, default=500, help="Maximum wallets to scan this run")
    parser.add_argument("--top-n", type=int, default=50, help="Recommended wallet count to output")
    parser.add_argument("--api-sleep", type=float, default=2.5, help="Sleep seconds after each wallet scan")
    parser.add_argument("--min-account-value", type=float, default=25.0, help="Minimum account value for qualified wallets")
    parser.add_argument("--min-fills", type=int, default=1, help="Minimum fills for qualified wallets")
    parser.add_argument("--candidate-file", action="append", default=[], help="Extra candidate wallet file")
    parser.add_argument("--scan-path", action="append", default=[], help="Extra path to scan for wallet addresses")
    parser.add_argument("--skip-vault-candidates", action="store_true", help="Skip public Hyperliquid vault candidate discovery")
    parser.add_argument("--max-file-mb", type=int, default=5, help="Max text file size scanned for addresses")
    args = parser.parse_args()

    repo = Path(args.repo_root).expanduser().resolve()
    script_dir = Path(__file__).resolve().parent
    out_root = repo / "copycat_daily_scout_out_v2"
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S_UTC")
    run_dir = out_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    candidates: dict[str, set[str]] = {}

    default_files = [
        script_dir / "candidate_wallets.txt",
        repo / "scripts" / "local_snapshot_publisher" / "wallets.txt",
        Path(r"C:\CopycatSnapshotPublisher\local_snapshot_publisher\wallets.txt"),
    ]
    for file_path in default_files:
        read_candidate_file(file_path, candidates, str(file_path))

    for file_arg in args.candidate_file:
        read_candidate_file(Path(file_arg).expanduser(), candidates, file_arg)

    scan_paths = [repo]
    old_onedrive = Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop" / "hyper_wallet_tracker_saas_v1_OLD_DO_NOT_USE"
    if old_onedrive.exists():
        scan_paths.append(old_onedrive)
    for scan_arg in args.scan_path:
        scan_paths.append(Path(scan_arg).expanduser())

    print("Discovering candidate wallets from local files...")
    for scan_path in scan_paths:
        print(f"Scanning for wallet addresses in: {scan_path}")
        scan_path_for_candidates(scan_path, candidates, max_file_mb=args.max_file_mb)

    vault_added = 0
    if not args.skip_vault_candidates:
        print("Fetching public Hyperliquid vault candidate addresses...")
        vault_added = fetch_vault_candidates(candidates)

    sorted_candidates = sorted(candidates.keys())
    selected = sorted_candidates[: max(args.max_scan, 0)]

    print("")
    print(f"Candidate wallets discovered: {len(sorted_candidates)}")
    print(f"Vault candidates added: {vault_added}")
    print(f"Wallets selected for this scan: {len(selected)} / max {args.max_scan}")
    print("")

    rows: list[dict[str, Any]] = []
    started = time.time()

    for idx, address in enumerate(selected, start=1):
        print(f"[{idx}/{len(selected)}] Scanning {address}")
        row = score_wallet(address, min_account_value=args.min_account_value, min_fills=args.min_fills)
        row["sources"] = ";".join(sorted(candidates.get(address, [])))[:2000]
        rows.append(row)

        if args.api_sleep > 0 and idx < len(selected):
            time.sleep(args.api_sleep)

    ranked = sorted(rows, key=lambda r: (bool(r.get("qualified")), safe_float(r.get("score"))), reverse=True)
    qualified = [r for r in ranked if r.get("qualified")]
    recommended = qualified[: args.top_n]

    write_csv(run_dir / "wallet_scorecards.csv", ranked)
    (run_dir / "candidate_wallets_scanned.txt").write_text("\n".join(selected) + "\n", encoding="utf-8")
    (run_dir / "recommended_wallets_top50.txt").write_text(
        "\n".join(str(r["address"]) for r in recommended) + ("\n" if recommended else ""),
        encoding="utf-8",
    )

    elapsed = round(time.time() - started, 2)
    summary = {
        "run_started_utc": timestamp,
        "candidate_wallets_discovered": len(sorted_candidates),
        "vault_candidates_added": vault_added,
        "wallets_scanned": len(selected),
        "max_scan": args.max_scan,
        "qualified_wallets": len(qualified),
        "recommended_wallets": len(recommended),
        "top_n": args.top_n,
        "api_sleep_seconds": args.api_sleep,
        "elapsed_seconds": elapsed,
        "top_claim_ready": len(sorted_candidates) >= 5000 and len(qualified) >= args.top_n,
        "scope_label": f"Top {len(recommended)} Copycat-ranked wallets from {len(selected)} scanned / {len(qualified)} qualified wallet candidates",
        "notes": [
            "This scanner does not change the live publisher automatically.",
            "It writes local recommendations only.",
            "Apply recommended wallets to the live publisher only after manual review."
        ],
    }
    (run_dir / "scan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    next_steps = f"""Copycat Daily Scout v2 results

Run folder:
{run_dir}

Scanned:
{len(selected)} wallet(s)

Qualified:
{len(qualified)} wallet(s)

Recommended:
{len(recommended)} wallet(s)

Recommended wallet file:
{run_dir / "recommended_wallets_top50.txt"}

Important:
This did NOT modify the live Snapshot Publisher.
Review wallet_scorecards.csv before applying anything live.
"""
    (run_dir / "README_NEXT_STEPS.txt").write_text(next_steps, encoding="utf-8")
    copy_latest_outputs(run_dir, out_root)

    print("")
    print(json.dumps(summary, indent=2))
    print("")
    print(f"Results written to: {run_dir}")
    print(f"Latest copy written to: {out_root / 'latest'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

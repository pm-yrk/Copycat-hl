#!/usr/bin/env python3
"""
Copycat Top-50 Integrity V1.

Reads the existing Copycat wallet registry, builds one conservative
profit-quality ranking, and safely updates only the active publisher's
wallets.txt when at least 50 wallets meet the minimum rules.

Runtime files are kept outside Git in the active publisher scanner_state.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

METHOD_VERSION = "copycat_top50_integrity_v1"
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ZERO_ADDRESS = "0x" + ("0" * 40)

MIN_ACCOUNT_VALUE = 1_000.0
MIN_FILLS = 5
MIN_WIN_RATE = 0.50
MAX_SCAN_AGE_HOURS = 72
TARGET_SIZE = 50
CORE_ENTRY_RANK = 45
RETENTION_RANK = 60


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text(value: dt.datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def valid_wallet(value: Any) -> bool:
    address = str(value or "").strip().lower()
    return bool(ADDRESS_RE.fullmatch(address)) and address != ZERO_ADDRESS


def percentile_map(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.values())
    if len(ordered) == 1:
        return {key: 0.5 for key in values}
    result: dict[str, float] = {}
    for key, value in values.items():
        left = 0
        right = len(ordered)
        while left < right:
            middle = (left + right) // 2
            if ordered[middle] <= value:
                left = middle + 1
            else:
                right = middle
        result[key] = max(0.0, min(1.0, (left - 1) / (len(ordered) - 1)))
    return result


def load_registry(db_path: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        wallet_rows = [
            dict(row)
            for row in con.execute(
                """
                SELECT address, first_seen_utc, last_seen_utc, discovery_count,
                       last_scanned_utc, scan_count, ok, qualified,
                       account_value, withdrawable, open_positions,
                       position_value, unrealized_pnl, fills_count,
                       active_symbols, closed_pnl, wins, losses,
                       win_rate, copycat_score, last_error, updated_utc
                FROM wallets
                """
            ).fetchall()
        ]
        history: dict[str, list[dict[str, Any]]] = {}
        for row in con.execute(
            """
            SELECT address, scanned_utc, ok, qualified, account_value,
                   closed_pnl, fills_count, copycat_score, error
            FROM scan_history
            WHERE ok=1
            ORDER BY address, scanned_utc
            """
        ).fetchall():
            item = dict(row)
            address = str(item.get("address") or "").lower()
            history.setdefault(address, []).append(item)
        return wallet_rows, history
    finally:
        con.close()


def history_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    good = [row for row in rows if safe_int(row.get("ok")) == 1]
    if not good:
        return {
            "history_scans": 0,
            "consistency": 0.5,
            "drawdown_control": 0.5,
        }

    pnl_values = [safe_float(row.get("closed_pnl")) for row in good]
    positive_share = sum(1 for value in pnl_values if value > 0) / len(pnl_values)
    confidence = min(1.0, len(good) / 7.0)
    consistency = (0.5 * (1.0 - confidence)) + (positive_share * confidence)

    account_values = [
        safe_float(row.get("account_value"))
        for row in good
        if safe_float(row.get("account_value")) > 0
    ]
    if len(account_values) < 2:
        drawdown_control = 0.5
    else:
        peak = account_values[0]
        max_drawdown = 0.0
        for value in account_values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
        drawdown_control = max(0.0, min(1.0, 1.0 - min(max_drawdown, 1.0)))

    return {
        "history_scans": len(good),
        "consistency": consistency,
        "drawdown_control": drawdown_control,
    }


def prepare_candidates(
    wallets: list[dict[str, Any]],
    history: dict[str, list[dict[str, Any]]],
    now: dt.datetime,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates: list[dict[str, Any]] = []
    reasons = {
        "invalid_address": 0,
        "not_ok": 0,
        "stale": 0,
        "small_account": 0,
        "too_few_fills": 0,
        "non_positive_profit": 0,
        "low_win_rate": 0,
    }

    for row in wallets:
        address = str(row.get("address") or "").strip().lower()
        if not valid_wallet(address):
            reasons["invalid_address"] += 1
            continue
        if safe_int(row.get("ok")) != 1:
            reasons["not_ok"] += 1
            continue

        scanned = parse_utc(row.get("last_scanned_utc") or row.get("updated_utc"))
        age_hours = (
            (now - scanned).total_seconds() / 3600.0
            if scanned is not None
            else 999999.0
        )
        if age_hours > MAX_SCAN_AGE_HOURS:
            reasons["stale"] += 1
            continue

        account = safe_float(row.get("account_value"))
        fills = safe_int(row.get("fills_count"))
        closed_pnl = safe_float(row.get("closed_pnl"))
        wins = safe_int(row.get("wins"))
        losses = safe_int(row.get("losses"))
        observed_trades = max(fills, wins + losses)
        raw_win_rate = safe_float(row.get("win_rate"))
        if raw_win_rate > 1.0:
            raw_win_rate /= 100.0
        if wins + losses > 0:
            raw_win_rate = wins / max(1, wins + losses)

        if account < MIN_ACCOUNT_VALUE:
            reasons["small_account"] += 1
            continue
        if observed_trades < MIN_FILLS:
            reasons["too_few_fills"] += 1
            continue
        if closed_pnl <= 0:
            reasons["non_positive_profit"] += 1
            continue
        if raw_win_rate < MIN_WIN_RATE:
            reasons["low_win_rate"] += 1
            continue

        # Bayesian win-rate adjustment: small samples are pulled toward 50%.
        adjusted_win_rate = (wins + 5.0) / max(10.0, wins + losses + 10.0)
        roi = closed_pnl / max(account, MIN_ACCOUNT_VALUE)
        exposure_ratio = safe_float(row.get("position_value")) / max(account, 1.0)
        risk_penalty = max(0.0, min(1.0, (exposure_ratio - 3.0) / 7.0))
        activity = min(1.0, math.log1p(observed_trades) / math.log(201.0))
        diversity = min(1.0, safe_int(row.get("active_symbols")) / 5.0)
        sample_quality = (activity * 0.75) + (diversity * 0.25)
        hist = history_metrics(history.get(address, []))

        candidates.append(
            {
                **row,
                "address": address,
                "account_value": account,
                "fills_count": fills,
                "observed_trades": observed_trades,
                "closed_pnl": closed_pnl,
                "win_rate_adjusted": adjusted_win_rate,
                "roi": roi,
                "risk_penalty": risk_penalty,
                "sample_quality": sample_quality,
                "age_hours": age_hours,
                **hist,
            }
        )

    return candidates, reasons


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profit_pct = percentile_map(
        {row["address"]: math.log1p(max(0.0, row["closed_pnl"])) for row in candidates}
    )
    roi_pct = percentile_map(
        {row["address"]: max(-1.0, min(2.0, row["roi"])) for row in candidates}
    )

    ranked: list[dict[str, Any]] = []
    for row in candidates:
        address = row["address"]
        score = (
            30.0 * profit_pct.get(address, 0.0)
            + 25.0 * roi_pct.get(address, 0.0)
            + 15.0 * row["win_rate_adjusted"]
            + 15.0 * row["consistency"]
            + 10.0 * row["drawdown_control"]
            + 5.0 * row["sample_quality"]
            - 10.0 * row["risk_penalty"]
        )
        ranked.append(
            {
                **row,
                "profit_percentile": profit_pct.get(address, 0.0),
                "roi_percentile": roi_pct.get(address, 0.0),
                "integrity_score": round(max(0.0, min(100.0, score)), 4),
            }
        )

    ranked.sort(
        key=lambda row: (
            -safe_float(row.get("integrity_score")),
            -safe_float(row.get("closed_pnl")),
            -safe_float(row.get("account_value")),
            row.get("address") or "",
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["universe_rank"] = index
    return ranked


def read_wallet_file(path: Path) -> list[str]:
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


def choose_top50(ranked: list[dict[str, Any]], current: list[str]) -> list[dict[str, Any]]:
    by_address = {row["address"]: row for row in ranked}
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()

    # The strongest 45 must earn entry directly.
    for row in ranked[:CORE_ENTRY_RANK]:
        chosen.append(row)
        used.add(row["address"])

    # Existing members may remain while still ranked in the top 60.
    for address in current:
        row = by_address.get(address)
        if not row or row["address"] in used:
            continue
        if safe_int(row.get("universe_rank")) <= RETENTION_RANK and len(chosen) < TARGET_SIZE:
            chosen.append(row)
            used.add(row["address"])

    # Fill any remaining places by score.
    for row in ranked:
        if len(chosen) >= TARGET_SIZE:
            break
        if row["address"] in used:
            continue
        chosen.append(row)
        used.add(row["address"])

    chosen.sort(
        key=lambda row: (
            -safe_float(row.get("integrity_score")),
            -safe_float(row.get("closed_pnl")),
            row.get("address") or "",
        )
    )
    for index, row in enumerate(chosen, start=1):
        row["selected_rank"] = index
    return chosen[:TARGET_SIZE]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def write_outputs(
    active_dir: Path,
    ranked: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    reasons: dict[str, int],
    current: list[str],
    applied: bool,
    status: str,
) -> dict[str, Any]:
    state_dir = active_dir / "scanner_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    selected_addresses = [row["address"] for row in selected]
    current_set = set(current)
    selected_set = set(selected_addresses)

    report = {
        "status": status,
        "method_version": METHOD_VERSION,
        "generated_at_utc": utc_text(now),
        "generated_at_ms": int(now.timestamp() * 1000),
        "rules": {
            "minimum_account_value_usd": MIN_ACCOUNT_VALUE,
            "minimum_observed_fills": MIN_FILLS,
            "minimum_win_rate": MIN_WIN_RATE,
            "positive_closed_pnl_required": True,
            "maximum_scan_age_hours": MAX_SCAN_AGE_HOURS,
            "core_entry_rank": CORE_ENTRY_RANK,
            "retention_rank": RETENTION_RANK,
        },
        "weights": {
            "closed_profit": 30,
            "return_on_account": 25,
            "adjusted_win_rate": 15,
            "history_consistency": 15,
            "drawdown_control": 10,
            "sample_and_activity": 5,
            "excess_exposure_penalty": -10,
        },
        "qualified_candidates": len(ranked),
        "selected_wallet_count": len(selected),
        "applied": applied,
        "entered": sorted(selected_set - current_set),
        "exited": sorted(current_set - selected_set),
        "exclusion_counts": reasons,
        "selected": [
            {
                "rank": row.get("selected_rank"),
                "universe_rank": row.get("universe_rank"),
                "wallet": row.get("address"),
                "integrity_score": row.get("integrity_score"),
                "account_value_usd": round(safe_float(row.get("account_value")), 2),
                "closed_pnl_usd": round(safe_float(row.get("closed_pnl")), 2),
                "roi_pct": round(safe_float(row.get("roi")) * 100.0, 4),
                "win_rate_pct": round(safe_float(row.get("win_rate_adjusted")) * 100.0, 2),
                "history_scans": safe_int(row.get("history_scans")),
                "consistency_pct": round(safe_float(row.get("consistency")) * 100.0, 2),
                "drawdown_control_pct": round(
                    safe_float(row.get("drawdown_control")) * 100.0, 2
                ),
            }
            for row in selected
        ],
    }

    atomic_write_text(
        state_dir / "top50_integrity.json",
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )

    csv_path = state_dir / "top50_integrity_ranking.csv"
    fieldnames = [
        "universe_rank",
        "selected_rank",
        "address",
        "integrity_score",
        "account_value",
        "closed_pnl",
        "roi",
        "win_rate_adjusted",
        "history_scans",
        "consistency",
        "drawdown_control",
        "fills_count",
        "active_symbols",
        "age_hours",
    ]
    handle, temp_name = tempfile.mkstemp(prefix=csv_path.name + ".", suffix=".tmp", dir=str(state_dir))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            selected_rank = {
                row["address"]: row.get("selected_rank") for row in selected
            }
            for row in ranked:
                writer.writerow(
                    {
                        name: (
                            selected_rank.get(row["address"])
                            if name == "selected_rank"
                            else row.get(name)
                        )
                        for name in fieldnames
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, csv_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    return report


def update_scanner_results(active_dir: Path, report: dict[str, Any]) -> None:
    state_dir = active_dir / "scanner_state"
    path = state_dir / "scanner_results.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}

    selected = report.get("selected") or []
    payload = {
        "status": "ok",
        "source": METHOD_VERSION,
        "updated_at_ms": report.get("generated_at_ms"),
        "coins_scanned": existing.get("coins_scanned") or [],
        "recent_trades_seen": safe_int(existing.get("recent_trades_seen")),
        "wallets_discovered_from_recent_trades": safe_int(
            existing.get("wallets_discovered_from_recent_trades")
        ),
        "candidate_wallets_scored": report.get("qualified_candidates"),
        "candidate_wallet_errors": sum(
            safe_int(value) for value in (report.get("exclusion_counts") or {}).values()
        ),
        "selected_wallet_count": len(selected),
        "selected_wallets": [row.get("wallet") for row in selected],
        "top_rows": selected,
        "all_rows": [],
        "method_note": (
            "Copycat Top-50 Integrity V1: positive closed profit, return on account, "
            "adjusted win rate, observed consistency, drawdown control, sample quality, "
            "and a top-60 retention buffer. Ranked only from fresh qualified wallets "
            "inside Copycat's indexed universe."
        ),
    }
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def record_history(active_dir: Path, report: dict[str, Any]) -> None:
    path = active_dir / "scanner_state" / "top50_integrity.sqlite"
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                generated_at_utc TEXT NOT NULL,
                method_version TEXT NOT NULL,
                status TEXT NOT NULL,
                qualified_candidates INTEGER NOT NULL,
                selected_wallet_count INTEGER NOT NULL,
                applied INTEGER NOT NULL,
                report_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS members(
                run_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                wallet TEXT NOT NULL,
                score REAL NOT NULL,
                entered INTEGER NOT NULL,
                exited INTEGER NOT NULL DEFAULT 0,
                metrics_json TEXT NOT NULL,
                PRIMARY KEY(run_id, wallet)
            );
            """
        )
        cur = con.execute(
            """
            INSERT INTO runs(
                generated_at_utc, method_version, status,
                qualified_candidates, selected_wallet_count,
                applied, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.get("generated_at_utc"),
                METHOD_VERSION,
                report.get("status"),
                safe_int(report.get("qualified_candidates")),
                safe_int(report.get("selected_wallet_count")),
                1 if report.get("applied") else 0,
                json.dumps(report, separators=(",", ":"), ensure_ascii=False),
            ),
        )
        run_id = safe_int(cur.lastrowid)
        entered = set(report.get("entered") or [])
        for row in report.get("selected") or []:
            con.execute(
                """
                INSERT INTO members(
                    run_id, rank, wallet, score, entered, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    safe_int(row.get("rank")),
                    row.get("wallet"),
                    safe_float(row.get("integrity_score")),
                    1 if row.get("wallet") in entered else 0,
                    json.dumps(row, separators=(",", ":"), ensure_ascii=False),
                ),
            )
        con.commit()
    finally:
        con.close()


def self_test() -> None:
    now = utc_now()
    rows: list[dict[str, Any]] = []
    history: dict[str, list[dict[str, Any]]] = {}
    for index in range(80):
        address = "0x" + f"{index + 1:040x}"
        rows.append(
            {
                "address": address,
                "last_scanned_utc": utc_text(now - dt.timedelta(hours=1)),
                "updated_utc": utc_text(now),
                "ok": 1,
                "qualified": 1,
                "account_value": 10000 + index * 500,
                "position_value": 5000 + index * 100,
                "unrealized_pnl": 100,
                "fills_count": 20 + index,
                "active_symbols": 2 + (index % 4),
                "closed_pnl": 100 + index * 50,
                "wins": 15 + index,
                "losses": 5 + (index % 3),
                "win_rate": 0.70,
                "copycat_score": 1,
            }
        )
        history[address] = [
            {
                "ok": 1,
                "account_value": 10000 + index * 400,
                "closed_pnl": 50 + index * 20,
            },
            {
                "ok": 1,
                "account_value": 10100 + index * 450,
                "closed_pnl": 75 + index * 30,
            },
        ]

    candidates, reasons = prepare_candidates(rows, history, now)
    ranked = rank_candidates(candidates)
    selected = choose_top50(ranked, [row["address"] for row in ranked[48:58]])

    assert len(candidates) == 80, reasons
    assert len(selected) == 50
    assert len({row["address"] for row in selected}) == 50
    assert all(valid_wallet(row["address"]) for row in selected)
    assert selected[0]["integrity_score"] >= selected[-1]["integrity_score"]
    print("Top-50 Integrity V1 self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument(
        "--active-publisher",
        default=r"C:\CopycatSnapshotPublisher\local_snapshot_publisher",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = Path(args.repo_root).expanduser().resolve()
    active_dir = Path(args.active_publisher).expanduser().resolve()
    registry_db = repo / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite"
    wallet_file = active_dir / "wallets.txt"
    changed_flag = active_dir / "scanner_state" / "top50_integrity_changed.flag"

    changed_flag.unlink(missing_ok=True)

    if not registry_db.exists():
        raise SystemExit(f"Registry database not found: {registry_db}")
    if not active_dir.exists():
        raise SystemExit(f"Active publisher not found: {active_dir}")

    wallets, history = load_registry(registry_db)
    candidates, reasons = prepare_candidates(wallets, history, utc_now())
    ranked = rank_candidates(candidates)
    current = read_wallet_file(wallet_file)
    selected = choose_top50(ranked, current)

    if len(ranked) < TARGET_SIZE or len(selected) < TARGET_SIZE:
        report = write_outputs(
            active_dir,
            ranked,
            selected,
            reasons,
            current,
            applied=False,
            status="warming",
        )
        record_history(active_dir, report)
        print(
            f"SAFE HOLD: {len(ranked)} wallets meet the new rules; "
            f"{TARGET_SIZE} are required. The live wallet list was not changed."
        )
        return 0

    selected_addresses = [row["address"] for row in selected]
    changed = selected_addresses != current[:TARGET_SIZE]
    applied = False

    if args.apply and changed:
        backup_dir = Path(r"C:\CopycatBackups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%d-%H%M%S")
        if wallet_file.exists():
            shutil.copy2(
                wallet_file,
                backup_dir / f"wallets-before-top50-integrity-{stamp}.txt",
            )
        text = "\n".join(selected_addresses) + "\n"
        atomic_write_text(wallet_file, text)
        verified = read_wallet_file(wallet_file)
        if verified != selected_addresses:
            raise RuntimeError("The new live wallet file failed verification.")
        atomic_write_text(changed_flag, utc_text() + "\n")
        applied = True

    status = "applied" if applied else ("ready" if changed else "unchanged")
    report = write_outputs(
        active_dir,
        ranked,
        selected,
        reasons,
        current,
        applied=applied,
        status=status,
    )
    update_scanner_results(active_dir, report)
    record_history(active_dir, report)

    print(
        f"Qualified: {len(ranked)} | Selected: {len(selected)} | "
        f"Entered: {len(report['entered'])} | Exited: {len(report['exited'])}"
    )
    if applied:
        print("The active publisher wallet list was updated safely.")
    elif changed:
        print("A new cohort is ready. Run again with --apply to activate it.")
    else:
        print("The active publisher already has the correct cohort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

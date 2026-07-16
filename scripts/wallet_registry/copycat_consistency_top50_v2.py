#!/usr/bin/env python3
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
import tempfile
import time
from pathlib import Path
from typing import Any

METHOD = "copycat_consistency_top50_v2"
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ZERO_ADDRESS = "0x" + ("0" * 40)

TARGET = 50
ENTRY_CORE = 45
RETENTION_RANK = 60

MIN_ACCOUNT_VALUE = 5_000.0
MIN_FILLS = 100
MIN_SPAN_DAYS = 30.0
MIN_ACTIVE_DAYS = 15
MIN_OBSERVED_WEEKS = 5
MIN_PROFITABLE_WEEKS = 4
MIN_PROFITABLE_WEEK_RATIO = 0.65
MIN_WIN_RATE = 0.52
MAX_LARGEST_WIN_SHARE = 0.35
MAX_METRIC_AGE_HOURS = 48


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


def percentile(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.values())
    if len(ordered) == 1:
        return {key: 0.5 for key in values}
    result: dict[str, float] = {}
    for key, value in values.items():
        position = sum(1 for item in ordered if item <= value) - 1
        result[key] = max(0.0, min(1.0, position / (len(ordered) - 1)))
    return result


def connect_db(repo: Path) -> sqlite3.Connection:
    path = repo / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite"
    if not path.exists():
        raise FileNotFoundError(path)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS consistency_top50_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            indexed_wallets INTEGER NOT NULL,
            deeply_scored_wallets INTEGER NOT NULL,
            qualified_wallets INTEGER NOT NULL,
            selected_wallets INTEGER NOT NULL,
            applied INTEGER NOT NULL,
            report_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consistency_top50_members (
            run_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            wallet TEXT NOT NULL,
            score REAL NOT NULL,
            entered INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            PRIMARY KEY(run_id, wallet)
        );
        """
    )
    con.commit()
    return con


def load_rows(con: sqlite3.Connection) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = [
        dict(row)
        for row in con.execute(
            """
            SELECT *
            FROM wallet_profit_metrics
            WHERE score_ready=1
            """
        ).fetchall()
    ]
    counts = {
        "indexed_wallets": int(con.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]),
        "deeply_scored_wallets": len(rows),
    }
    return rows, counts


def qualify(rows: list[dict[str, Any]], now: dt.datetime) -> tuple[list[dict[str, Any]], dict[str, int]]:
    qualified: list[dict[str, Any]] = []
    excluded = {
        "invalid_address": 0,
        "stale_metrics": 0,
        "small_account": 0,
        "too_few_fills": 0,
        "short_history": 0,
        "too_few_active_days": 0,
        "too_few_weeks": 0,
        "not_enough_profitable_weeks": 0,
        "low_weekly_consistency": 0,
        "low_win_rate": 0,
        "non_positive_net_profit": 0,
        "single_win_dominance": 0,
    }
    for row in rows:
        address = str(row.get("address") or "").lower()
        if not valid_wallet(address):
            excluded["invalid_address"] += 1
            continue
        observed = parse_utc(row.get("observed_at_utc"))
        age_hours = (now - observed).total_seconds() / 3600 if observed else 999999
        checks = [
            ("stale_metrics", age_hours > MAX_METRIC_AGE_HOURS),
            ("small_account", safe_float(row.get("account_value")) < MIN_ACCOUNT_VALUE),
            ("too_few_fills", safe_int(row.get("fill_count")) < MIN_FILLS),
            ("short_history", safe_float(row.get("span_days")) < MIN_SPAN_DAYS),
            ("too_few_active_days", safe_int(row.get("active_days")) < MIN_ACTIVE_DAYS),
            ("too_few_weeks", safe_int(row.get("observed_weeks")) < MIN_OBSERVED_WEEKS),
            (
                "not_enough_profitable_weeks",
                safe_int(row.get("profitable_weeks")) < MIN_PROFITABLE_WEEKS,
            ),
            (
                "low_weekly_consistency",
                safe_float(row.get("profitable_week_ratio")) < MIN_PROFITABLE_WEEK_RATIO,
            ),
            ("low_win_rate", safe_float(row.get("win_rate")) < MIN_WIN_RATE),
            ("non_positive_net_profit", safe_float(row.get("net_pnl")) <= 0),
            (
                "single_win_dominance",
                safe_float(row.get("largest_win_share")) > MAX_LARGEST_WIN_SHARE,
            ),
        ]
        failed = next((name for name, is_failed in checks if is_failed), None)
        if failed:
            excluded[failed] += 1
            continue
        row["address"] = address
        row["metric_age_hours"] = age_hours
        qualified.append(row)
    return qualified, excluded


def rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    net_pct = percentile(
        {row["address"]: math.log1p(max(0.0, safe_float(row.get("net_pnl")))) for row in rows}
    )
    roi_pct = percentile(
        {
            row["address"]: safe_float(row.get("net_pnl"))
            / max(safe_float(row.get("account_value")), 1.0)
            for row in rows
        }
    )
    ranked: list[dict[str, Any]] = []
    for row in rows:
        address = row["address"]
        week_consistency = safe_float(row.get("profitable_week_ratio"))
        win_rate = safe_float(row.get("win_rate"))
        sample_quality = min(1.0, safe_int(row.get("fill_count")) / 500.0)
        active_quality = min(1.0, safe_int(row.get("active_days")) / 45.0)
        diversification = max(0.0, 1.0 - safe_float(row.get("largest_win_share")) / MAX_LARGEST_WIN_SHARE)
        drawdown_proxy = max(
            0.0,
            1.0
            - safe_float(row.get("worst_day_loss"))
            / max(safe_float(row.get("gross_profit")), 1.0),
        )
        score = (
            25 * net_pct.get(address, 0.0)
            + 20 * roi_pct.get(address, 0.0)
            + 20 * week_consistency
            + 10 * win_rate
            + 10 * ((sample_quality + active_quality) / 2)
            + 10 * diversification
            + 5 * drawdown_proxy
        )
        ranked.append(
            {
                **row,
                "roi": safe_float(row.get("net_pnl"))
                / max(safe_float(row.get("account_value")), 1.0),
                "consistency_score": round(max(0.0, min(100.0, score)), 4),
            }
        )
    ranked.sort(
        key=lambda row: (
            -safe_float(row.get("consistency_score")),
            -safe_float(row.get("net_pnl")),
            -safe_float(row.get("account_value")),
            row["address"],
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["universe_rank"] = index
    return ranked


def read_wallets(path: Path) -> list[str]:
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


def select(ranked: list[dict[str, Any]], current: list[str]) -> list[dict[str, Any]]:
    by_address = {row["address"]: row for row in ranked}
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()

    for row in ranked[:ENTRY_CORE]:
        chosen.append(row)
        used.add(row["address"])

    for address in current:
        row = by_address.get(address)
        if row and row["address"] not in used and safe_int(row.get("universe_rank")) <= RETENTION_RANK:
            chosen.append(row)
            used.add(row["address"])
            if len(chosen) >= TARGET:
                break

    for row in ranked:
        if len(chosen) >= TARGET:
            break
        if row["address"] in used:
            continue
        chosen.append(row)
        used.add(row["address"])

    chosen.sort(
        key=lambda row: (
            -safe_float(row.get("consistency_score")),
            -safe_float(row.get("net_pnl")),
            row["address"],
        )
    )
    for index, row in enumerate(chosen, start=1):
        row["selected_rank"] = index
    return chosen[:TARGET]


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def compact_member(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": safe_int(row.get("selected_rank")),
        "universe_rank": safe_int(row.get("universe_rank")),
        "wallet": row.get("address"),
        "score": safe_float(row.get("consistency_score")),
        "net_pnl_usd": round(safe_float(row.get("net_pnl")), 2),
        "account_value_usd": round(safe_float(row.get("account_value")), 2),
        "roi_pct": round(safe_float(row.get("roi")) * 100, 4),
        "fills": safe_int(row.get("fill_count")),
        "active_days": safe_int(row.get("active_days")),
        "profitable_weeks": safe_int(row.get("profitable_weeks")),
        "observed_weeks": safe_int(row.get("observed_weeks")),
        "win_rate_pct": round(safe_float(row.get("win_rate")) * 100, 2),
        "largest_win_share_pct": round(safe_float(row.get("largest_win_share")) * 100, 2),
    }


def write_report(
    repo: Path,
    active: Path,
    counts: dict[str, int],
    ranked: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    excluded: dict[str, int],
    current: list[str],
    status: str,
    applied: bool,
) -> dict[str, Any]:
    current_set = set(current)
    selected_addresses = [row["address"] for row in selected]
    selected_set = set(selected_addresses)
    report = {
        "status": status,
        "method": METHOD,
        "generated_at_utc": utc_text(),
        "generated_at_ms": int(time.time() * 1000),
        **counts,
        "qualified_wallets": len(ranked),
        "selected_wallets": len(selected),
        "applied": applied,
        "entered": sorted(selected_set - current_set),
        "exited": sorted(current_set - selected_set),
        "rules": {
            "minimum_account_value_usd": MIN_ACCOUNT_VALUE,
            "minimum_fills": MIN_FILLS,
            "minimum_history_days": MIN_SPAN_DAYS,
            "minimum_active_days": MIN_ACTIVE_DAYS,
            "minimum_observed_weeks": MIN_OBSERVED_WEEKS,
            "minimum_profitable_weeks": MIN_PROFITABLE_WEEKS,
            "minimum_profitable_week_ratio": MIN_PROFITABLE_WEEK_RATIO,
            "minimum_win_rate": MIN_WIN_RATE,
            "maximum_largest_win_share": MAX_LARGEST_WIN_SHARE,
            "maximum_metric_age_hours": MAX_METRIC_AGE_HOURS,
        },
        "excluded": excluded,
        "selected": [compact_member(row) for row in selected],
        "note": (
            "Strict consistency ranking from Copycat's indexed universe. "
            "The live cohort is held unchanged until at least 50 wallets pass every rule."
        ),
    }
    for path in [
        repo / "copycat_wallet_registry" / "consistency_top50_status.json",
        active / "scanner_state" / "consistency_top50_status.json",
    ]:
        atomic_text(path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    csv_path = repo / "copycat_wallet_registry" / "consistency_top50_ranking.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        fields = list(compact_member(selected[0]).keys()) if selected else ["rank", "wallet"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in selected:
            writer.writerow(compact_member(row))
    return report


def update_scanner_results(active: Path, report: dict[str, Any]) -> None:
    path = active / "scanner_state" / "scanner_results.json"
    selected = report.get("selected") or []
    payload = {
        "status": report.get("status"),
        "source": METHOD,
        "updated_at_ms": report.get("generated_at_ms"),
        "candidate_wallets_scored": report.get("deeply_scored_wallets"),
        "wallets_discovered_from_recent_trades": report.get("indexed_wallets"),
        "selected_wallet_count": len(selected),
        "selected_wallets": [row.get("wallet") for row in selected],
        "top_rows": selected,
        "all_rows": [],
        "method_note": (
            "Strict Copycat consistency ranking: 100+ fills, 30+ days, "
            "15+ active days, at least 4 profitable weeks, 65% profitable-week ratio, "
            "52% win rate, positive net profit after fees and funding, "
            "and no single winning fill above 35% of gross profit."
        ),
    }
    atomic_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def record_run(con: sqlite3.Connection, report: dict[str, Any]) -> None:
    cur = con.execute(
        """
        INSERT INTO consistency_top50_runs(
            generated_at_utc, status, indexed_wallets, deeply_scored_wallets,
            qualified_wallets, selected_wallets, applied, report_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            report["generated_at_utc"],
            report["status"],
            safe_int(report.get("indexed_wallets")),
            safe_int(report.get("deeply_scored_wallets")),
            safe_int(report.get("qualified_wallets")),
            safe_int(report.get("selected_wallets")),
            1 if report.get("applied") else 0,
            json.dumps(report, separators=(",", ":"), ensure_ascii=False),
        ),
    )
    run_id = safe_int(cur.lastrowid)
    entered = set(report.get("entered") or [])
    for member in report.get("selected") or []:
        con.execute(
            """
            INSERT INTO consistency_top50_members(
                run_id, rank, wallet, score, entered, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                safe_int(member.get("rank")),
                member.get("wallet"),
                safe_float(member.get("score")),
                1 if member.get("wallet") in entered else 0,
                json.dumps(member, separators=(",", ":"), ensure_ascii=False),
            ),
        )
    con.commit()


def self_test() -> None:
    now = utc_now()
    rows: list[dict[str, Any]] = []
    for index in range(80):
        rows.append(
            {
                "address": "0x" + f"{index + 1:040x}",
                "observed_at_utc": utc_text(now),
                "account_value": 10000 + index * 1000,
                "fill_count": 150 + index,
                "span_days": 60,
                "active_days": 30,
                "observed_weeks": 9,
                "profitable_weeks": 7,
                "profitable_week_ratio": 7 / 9,
                "win_rate": 0.58,
                "net_pnl": 500 + index * 100,
                "largest_win_share": 0.12,
                "worst_day_loss": 100,
                "gross_profit": 3000,
            }
        )
    qualified, excluded = qualify(rows, now)
    ranked = rank(qualified)
    chosen = select(ranked, [row["address"] for row in ranked[48:58]])
    assert len(qualified) == 80, excluded
    assert len(chosen) == 50
    assert len({row["address"] for row in chosen}) == 50
    assert chosen[0]["consistency_score"] >= chosen[-1]["consistency_score"]
    print("Consistency Top-50 V2 self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=r"C:\dev\hyper_wallet_tracker_saas_v1")
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
    active = Path(args.active_publisher).expanduser().resolve()
    wallet_path = active / "wallets.txt"
    changed_flag = active / "scanner_state" / "consistency_top50_changed.flag"
    changed_flag.unlink(missing_ok=True)

    con = connect_db(repo)
    try:
        metric_rows, counts = load_rows(con)
        qualified, excluded = qualify(metric_rows, utc_now())
        ranked = rank(qualified)
        current = read_wallets(wallet_path)
        selected = select(ranked, current)

        if len(ranked) < TARGET:
            report = write_report(
                repo, active, counts, ranked, selected, excluded, current, "warming", False
            )
            update_scanner_results(active, report)
            record_run(con, report)
            print(
                f"SAFE HOLD: {len(ranked)} wallets pass all strict rules; "
                f"{TARGET} are required. The current live 50 were not changed."
            )
            return 0

        selected_addresses = [row["address"] for row in selected]
        changed = selected_addresses != current[:TARGET]
        applied = False
        if args.apply and changed:
            backup_dir = Path(r"C:\CopycatBackups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = utc_now().strftime("%Y%m%d-%H%M%S")
            if wallet_path.exists():
                shutil.copy2(
                    wallet_path,
                    backup_dir / f"wallets-before-consistency-v2-{stamp}.txt",
                )
            atomic_text(wallet_path, "\n".join(selected_addresses) + "\n")
            if read_wallets(wallet_path) != selected_addresses:
                raise RuntimeError("New live wallet file failed verification.")
            atomic_text(changed_flag, utc_text() + "\n")
            applied = True

        status = "applied" if applied else ("ready" if changed else "unchanged")
        report = write_report(
            repo, active, counts, ranked, selected, excluded, current, status, applied
        )
        update_scanner_results(active, report)
        record_run(con, report)
        print(
            f"Indexed {counts['indexed_wallets']:,} | "
            f"deeply scored {counts['deeply_scored_wallets']:,} | "
            f"qualified {len(ranked):,} | selected {len(selected)}"
        )
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

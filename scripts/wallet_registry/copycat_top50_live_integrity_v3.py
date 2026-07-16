#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
ZERO_ADDRESS = "0x" + ("0" * 40)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_text() -> str:
    return utc_now().isoformat(timespec="seconds")


def valid_wallet(value: Any) -> bool:
    address = str(value or "").strip().lower()
    return bool(ADDRESS_RE.fullmatch(address)) and address != ZERO_ADDRESS


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


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as stream:
        temp = Path(stream.name)
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
    temp.replace(path)


def check(repo: Path, active: Path) -> dict[str, Any]:
    status_path = repo / "copycat_wallet_registry" / "consistency_top50_status.json"
    db_path = repo / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite"
    wallet_path = active / "wallets.txt"

    if not status_path.exists():
        raise FileNotFoundError(status_path)
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    status = json.loads(status_path.read_text(encoding="utf-8"))
    selected = [
        str(row.get("wallet") or "").lower()
        for row in status.get("selected") or []
        if valid_wallet(row.get("wallet"))
    ]
    active_wallets = read_wallets(wallet_path)
    qualified = int(status.get("qualified_wallets") or 0)
    complete_count = int(status.get("deeply_scored_wallets") or 0)
    incomplete_count = int(status.get("incomplete_history_wallets") or 0)

    verified = qualified >= 50
    errors: list[str] = []
    if len(active_wallets) != 50:
        errors.append(f"active wallet file contains {len(active_wallets)} valid unique wallets")
    if verified:
        if len(selected) != 50:
            errors.append(f"strict ranking selected {len(selected)} wallets instead of 50")
        if active_wallets != selected:
            errors.append("active wallets do not exactly match the strict ranked top 50")

        con = sqlite3.connect(db_path, timeout=30)
        try:
            placeholders = ",".join("?" for _ in selected)
            if selected:
                rows = con.execute(
                    f"""
                    SELECT address, score_ready, history_complete
                    FROM wallet_profit_metrics
                    WHERE address IN ({placeholders})
                    """,
                    selected,
                ).fetchall()
                by_address = {str(row[0]).lower(): (int(row[1]), int(row[2])) for row in rows}
                for address in selected:
                    state = by_address.get(address)
                    if state != (1, 1):
                        errors.append(f"selected wallet lacks complete verified history: {address}")
            else:
                errors.append("verified status has no selected wallets")
        finally:
            con.close()

    payload = {
        "status": "verified" if verified and not errors else ("warming" if not verified else "error"),
        "checked_at_utc": utc_text(),
        "indexed_wallets": int(status.get("indexed_wallets") or 0),
        "analysed_wallets_total": int(status.get("analysed_wallets_total") or 0),
        "complete_histories": complete_count,
        "incomplete_histories": incomplete_count,
        "strict_qualified_wallets": qualified,
        "strict_selected_wallets": len(selected),
        "active_wallets": len(active_wallets),
        "active_matches_strict_top50": bool(verified and active_wallets == selected),
        "errors": errors,
        "note": (
            "Wallet-derived dashboard data is sourced from the exact strict top 50."
            if verified and not errors
            else "The current cohort is held until 50 complete histories pass every strict rule."
        ),
    }

    for path in [
        repo / "copycat_wallet_registry" / "top50_live_integrity.json",
        active / "scanner_state" / "top50_live_integrity.json",
    ]:
        atomic_json(path, payload)

    if errors:
        raise RuntimeError("; ".join(errors))
    return payload


def self_test() -> None:
    assert valid_wallet("0x" + "1" * 40)
    assert not valid_wallet(ZERO_ADDRESS)
    assert not valid_wallet("bad")
    print("Top-50 live integrity self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=r"C:\dev\hyper_wallet_tracker_saas_v1")
    parser.add_argument(
        "--active-publisher",
        default=r"C:\CopycatSnapshotPublisher\local_snapshot_publisher",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    payload = check(Path(args.repo_root), Path(args.active_publisher))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

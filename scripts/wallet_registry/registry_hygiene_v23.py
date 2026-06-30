#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, datetime as dt, json, re, sqlite3
from pathlib import Path

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

def utc_stamp(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def file_stamp(): return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
def output_root(repo: Path) -> Path: return repo / "copycat_wallet_registry"
def db_path(repo: Path) -> Path: return output_root(repo) / "copycat_wallet_registry.sqlite"
def hygiene_dir(repo: Path) -> Path:
    p = output_root(repo) / "hygiene"; p.mkdir(parents=True, exist_ok=True); return p

def is_structural_non_wallet(address: str) -> bool:
    address = (address or "").lower().strip()
    if not ADDRESS_RE.fullmatch(address): return True
    body = address[2:]
    if len(set(body)) == 1: return True
    if re.fullmatch(r"0x200000000000000000000000000000000000[0-9a-f]{4}", address): return True
    return False

def load_blocklist(repo: Path) -> set[str]:
    blocklist = set(BUILTIN_BLOCKED_ADDRESSES)
    path = repo / "scripts" / "wallet_registry" / "address_blocklist.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#") and ADDRESS_RE.fullmatch(line): blocklist.add(line)
    return blocklist

def is_bad_address(address: str, blocklist: set[str]) -> bool:
    address = (address or "").lower().strip()
    return address in blocklist or is_structural_non_wallet(address)

def connect_db(repo: Path) -> sqlite3.Connection:
    path = db_path(repo)
    if not path.exists(): raise FileNotFoundError(f"Registry database not found: {path}")
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; return conn

def table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def export_rows(repo: Path, rows, dry_run: bool) -> Path:
    out = hygiene_dir(repo) / f"{'dry_run_' if dry_run else ''}removed_addresses_{file_stamp()}.csv"
    fields = list(rows[0].keys()) if rows else ["address"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows: w.writerow(dict(row))
    return out

def delete_rows(conn, rows) -> int:
    removed = 0
    for row in rows:
        a = row["address"]
        cur = conn.execute("DELETE FROM wallets WHERE address=?", (a,))
        if table_exists(conn, "discoveries"): conn.execute("DELETE FROM discoveries WHERE address=?", (a,))
        if table_exists(conn, "scan_history"): conn.execute("DELETE FROM scan_history WHERE address=?", (a,))
        removed += cur.rowcount
    conn.commit(); return removed

def run(args):
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect_db(repo); blocklist = load_blocklist(repo)
    before_total = conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"]
    before_scanned = conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"]
    rows = conn.execute("SELECT * FROM wallets ORDER BY address").fetchall()
    bad = [r for r in rows if is_bad_address(r["address"], blocklist)]
    export_path = export_rows(repo, bad, args.dry_run)
    removed = 0 if args.dry_run else delete_rows(conn, bad)
    after_total = conn.execute("SELECT COUNT(*) AS n FROM wallets").fetchone()["n"]
    after_scanned = conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"]
    qualified = conn.execute("SELECT COUNT(*) AS n FROM wallets WHERE qualified=1").fetchone()["n"]
    summary = {"mode":"registry_hygiene_v23","dry_run":bool(args.dry_run),"wallets_before":before_total,
        "wallets_scanned_before":before_scanned,"bad_addresses_found":len(bad),"bad_addresses_removed":removed,
        "wallets_after":after_total,"wallets_scanned_after":after_scanned,"wallets_qualified_after":qualified,
        "removed_addresses_export":str(export_path),"database":str(db_path(repo)),"time_utc":utc_stamp(),
        "notes":["This removes obvious non-trader/system/token addresses from the local registry only.","It does not change live publisher wallets.","It does not touch the dashboard."]}
    summary_path = hygiene_dir(repo) / "hygiene_v23_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2)); print(f"Summary written to: {summary_path}")
    return 0

def main():
    p = argparse.ArgumentParser(description="Copycat registry hygiene v2.3")
    p.add_argument("--repo-root", default="."); p.add_argument("--dry-run", action="store_true")
    return run(p.parse_args())
if __name__ == "__main__": raise SystemExit(main())

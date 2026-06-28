#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, datetime as dt, json, re, sqlite3, time, zipfile
from pathlib import Path
from urllib import request

ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
TEXT_EXT = {".txt",".csv",".json",".jsonl",".md",".py",".ts",".tsx",".js",".jsx",".env",".example",".yaml",".yml",".log",".html",".htm"}
DEFAULT_URLS = [
    "https://hypertracker.io/",
    "https://hyperdash.com/learn/best-tools-trading-hyperliquid",
    "https://hyperdash.com/learn/what-is-copy-trading-how-it-works-and-what-to-watch-out-for",
]

def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def out_root(repo: Path) -> Path:
    p = repo / "copycat_wallet_registry"
    p.mkdir(parents=True, exist_ok=True)
    return p

def db_file(repo: Path) -> Path:
    return out_root(repo) / "copycat_wallet_registry.sqlite"

def connect(repo: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file(repo))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
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
    CREATE INDEX IF NOT EXISTS idx_wallets_score ON wallets(copycat_score DESC);
    CREATE INDEX IF NOT EXISTS idx_wallets_last_scanned ON wallets(last_scanned_utc);
    """)
    conn.commit()
    return conn

def blocklist(repo: Path) -> set[str]:
    p = repo / "scripts" / "wallet_registry" / "address_blocklist.txt"
    s = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#") and ADDRESS_RE.fullmatch(line):
                s.add(line)
    return s

def merge_source(existing: str, source: str) -> str:
    parts = [p for p in existing.split(";") if p]
    if source not in parts:
        parts.append(source)
    return ";".join(parts[:30])

def add_wallet(conn: sqlite3.Connection, address: str, source: str, now: str) -> bool:
    address = address.lower()
    row = conn.execute("SELECT sources FROM wallets WHERE address=?", (address,)).fetchone()
    if row:
        conn.execute("UPDATE wallets SET last_seen_utc=?, discovery_count=discovery_count+1, sources=?, updated_utc=? WHERE address=?",
                     (now, merge_source(row["sources"], source), now, address))
        new = False
    else:
        conn.execute("INSERT INTO wallets(address, first_seen_utc, last_seen_utc, discovery_count, sources, updated_utc) VALUES(?,?,?,?,?,?)",
                     (address, now, now, 1, source, now))
        new = True
    conn.execute("INSERT INTO discoveries(address, source, discovered_utc) VALUES(?,?,?)", (address, source[:1000], now))
    return new

def add_from_text(conn: sqlite3.Connection, text: str, source: str, blocked: set[str]) -> tuple[int,int]:
    addrs = {m.group(0).lower() for m in ADDRESS_RE.finditer(text)}
    addrs = {a for a in addrs if a not in blocked}
    new = 0
    now = utc()
    for a in addrs:
        if add_wallet(conn, a, source, now):
            new += 1
    return len(addrs), new

def scan_text_file(conn, path: Path, source: str, blocked: set[str], max_mb: int) -> tuple[int,int,bool]:
    try:
        if path.suffix.lower() not in TEXT_EXT or path.stat().st_size > max_mb*1024*1024:
            return 0,0,False
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0,0,False
    seen,new = add_from_text(conn, text, source, blocked)
    return seen,new,seen>0

def scan_zip(conn, path: Path, source: str, blocked: set[str], max_mb: int) -> tuple[int,int,int]:
    seen = new = members = 0
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if Path(info.filename).suffix.lower() not in TEXT_EXT or info.file_size > max_mb*1024*1024:
                    continue
                try:
                    text = z.read(info).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                s,n = add_from_text(conn, text, f"{source}:{path}!{info.filename}", blocked)
                if s:
                    seen += s; new += n; members += 1
    except Exception:
        pass
    return seen,new,members

def scan_path(conn, path: Path, source: str, blocked: set[str], max_mb: int, scan_zips: bool) -> dict:
    res = {"path": str(path), "files_scanned": 0, "zip_members_scanned": 0, "addresses_seen": 0, "new_wallets": 0}
    if not path.exists():
        return res
    items = [path] if path.is_file() else path.rglob("*")
    for p in items:
        if not p.is_file():
            continue
        s,n,ok = scan_text_file(conn, p, f"{source}:{p}", blocked, max_mb)
        if ok:
            res["files_scanned"] += 1; res["addresses_seen"] += s; res["new_wallets"] += n
        elif scan_zips and p.suffix.lower() == ".zip":
            s,n,m = scan_zip(conn, p, source, blocked, max_mb)
            if s:
                res["files_scanned"] += 1; res["zip_members_scanned"] += m; res["addresses_seen"] += s; res["new_wallets"] += n
    conn.commit()
    return res

def default_paths(repo: Path) -> list[Path]:
    paths = [
        repo / "copycat_daily_scout_out_v2",
        repo / "copycat_wallet_registry" / "imports",
        Path(r"C:\CopycatSnapshotPublisher\local_snapshot_publisher"),
        Path.home() / "Downloads",
        Path(r"C:\CopycatArchive"),
    ]
    return [p for p in paths if p.exists()]

def urls(repo: Path, include_defaults: bool) -> list[str]:
    out = DEFAULT_URLS[:] if include_defaults else []
    p = repo / "scripts" / "wallet_registry" / "wallet_source_urls.txt"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("http://") or line.startswith("https://"):
                out.append(line)
    seen, final = set(), []
    for u in out:
        if u not in seen:
            final.append(u); seen.add(u)
    return final

def fetch_url(url: str) -> str:
    req = request.Request(url, headers={"User-Agent":"CopycatWalletDiscoveryV22/1.0","Accept":"text/html,application/json,text/plain,*/*"})
    with request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")

def safe_name(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+","_",url)[:150]+".html"

def scan_urls(conn, repo: Path, blocked: set[str], include_defaults: bool, sleep_s: float) -> dict:
    cache = out_root(repo) / "web_cache"
    cache.mkdir(parents=True, exist_ok=True)
    res = {"urls_checked":0, "urls_with_addresses":0, "addresses_seen":0, "new_wallets":0, "errors":[]}
    for u in urls(repo, include_defaults):
        print(f"Fetching URL source: {u}")
        res["urls_checked"] += 1
        try:
            text = fetch_url(u)
            (cache / safe_name(u)).write_text(text, encoding="utf-8", errors="ignore")
            s,n = add_from_text(conn, text, f"url:{u}", blocked)
            if s:
                res["urls_with_addresses"] += 1; res["addresses_seen"] += s; res["new_wallets"] += n
                print(f"  found {s} address(es), {n} new")
            else:
                print("  no wallet-like addresses found")
            conn.commit()
        except Exception as exc:
            msg = f"{u}: {exc}"
            print(f"  skipped: {msg}")
            res["errors"].append(msg[:500])
        if sleep_s:
            time.sleep(sleep_s)
    return res

def purge_blocked(conn, blocked: set[str]) -> int:
    removed = 0
    for a in blocked:
        cur = conn.execute("DELETE FROM wallets WHERE address=?", (a,))
        conn.execute("DELETE FROM discoveries WHERE address=?", (a,))
        removed += cur.rowcount
    conn.commit()
    return removed

def export(conn, repo: Path):
    exp = out_root(repo) / "exports"
    exp.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("""SELECT address, first_seen_utc, last_seen_utc, discovery_count, sources,
        last_scanned_utc, scan_count, qualified, account_value, closed_pnl, copycat_score
        FROM wallets ORDER BY last_seen_utc DESC, discovery_count DESC""").fetchall()
    with (exp / "wallet_discovery_registry_export.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(rows[0].keys()) if rows else ["address"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow(dict(r))

def run_expand(args) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect(repo)
    imports = out_root(repo) / "imports"; imports.mkdir(parents=True, exist_ok=True)
    blocked = blocklist(repo)
    print("Copycat Wallet Discovery Expansion v2.2")
    print(f"Database: {db_file(repo)}")
    print(f"Imports folder: {imports}")
    removed = purge_blocked(conn, blocked) if args.purge_blocklist else 0
    if removed: print(f"Purged {removed} blocklisted address(es)")

    folder_results = []
    scan_paths = default_paths(repo) + [Path(x).expanduser() for x in (args.folder or [])]
    dedup, final_paths = set(), []
    for p in scan_paths:
        k = str(p).lower()
        if k not in dedup:
            dedup.add(k); final_paths.append(p)
    for p in final_paths:
        print(f"Scanning: {p}")
        r = scan_path(conn, p, "expanded_discovery", blocked, args.max_file_mb, not args.no_zip_scan)
        folder_results.append(r)
        print(f"  files={r['files_scanned']} zip_members={r['zip_members_scanned']} addresses={r['addresses_seen']} new={r['new_wallets']}")

    url_summary = {"urls_checked":0,"urls_with_addresses":0,"addresses_seen":0,"new_wallets":0,"errors":[]}
    if not args.skip_urls:
        url_summary = scan_urls(conn, repo, blocked, not args.no_default_urls, args.url_sleep)

    export(conn, repo)
    total = conn.execute("SELECT COUNT(*) n FROM wallets").fetchone()["n"]
    scanned = conn.execute("SELECT COUNT(*) n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"]
    qualified = conn.execute("SELECT COUNT(*) n FROM wallets WHERE qualified=1").fetchone()["n"]
    summary = {
        "mode":"expanded_discovery_v22",
        "wallets_total_in_registry": total,
        "wallets_scanned_ever": scanned,
        "wallets_qualified": qualified,
        "blocklisted_removed": removed,
        "folder_results": folder_results,
        "url_summary": url_summary,
        "database": str(db_file(repo)),
        "imports_folder": str(imports),
        "time_utc": utc(),
        "notes": [
            "This only discovers wallet addresses and updates the local registry.",
            "It does not score every wallet immediately.",
            "It does not change live publisher wallets.",
            "To grow fast, drop exported wallet lists, saved leaderboard pages, CSVs, or text files into the imports folder."
        ]
    }
    (out_root(repo) / "expanded_discovery_v22_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

def run_status(args) -> int:
    repo = Path(args.repo_root).expanduser().resolve()
    conn = connect(repo)
    summary = {
        "database": str(db_file(repo)),
        "wallets_total": conn.execute("SELECT COUNT(*) n FROM wallets").fetchone()["n"],
        "wallets_scanned_ever": conn.execute("SELECT COUNT(*) n FROM wallets WHERE last_scanned_utc IS NOT NULL").fetchone()["n"],
        "wallets_qualified": conn.execute("SELECT COUNT(*) n FROM wallets WHERE qualified=1").fetchone()["n"],
        "unscanned_wallets": conn.execute("SELECT COUNT(*) n FROM wallets WHERE last_scanned_utc IS NULL").fetchone()["n"],
        "imports_folder": str(out_root(repo) / "imports"),
    }
    print(json.dumps(summary, indent=2))
    return 0

def main() -> int:
    p = argparse.ArgumentParser(description="Copycat Wallet Discovery Expansion v2.2")
    p.add_argument("--repo-root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    e = sub.add_parser("expand")
    e.add_argument("--folder", action="append", default=[])
    e.add_argument("--max-file-mb", type=int, default=8)
    e.add_argument("--no-zip-scan", action="store_true")
    e.add_argument("--skip-urls", action="store_true")
    e.add_argument("--no-default-urls", action="store_true")
    e.add_argument("--url-sleep", type=float, default=1.5)
    e.add_argument("--purge-blocklist", action="store_true")
    e.set_defaults(func=run_expand)
    s = sub.add_parser("status")
    s.set_defaults(func=run_status)
    args = p.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())

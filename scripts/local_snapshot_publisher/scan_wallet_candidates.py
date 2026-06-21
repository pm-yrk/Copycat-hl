#!/usr/bin/env python3
"""
Copycat local wallet scanner v1.

Discovers recent Hyperliquid trader addresses from public recentTrades responses,
combines them with a local seed/candidate list, scores candidate wallets from
Hyperliquid clearinghouseState, and can update wallets.txt with the top selected wallets.

This is intentionally laptop-safe:
- no Supabase
- no historical backfill
- no growing database
- overwrites a compact scanner_state folder
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
DEFAULT_WALLET_FILE = SCRIPT_DIR / "wallets.txt"
DEFAULT_CANDIDATE_FILE = SCRIPT_DIR / "candidate_wallets.txt"
DEFAULT_STATE_DIR = SCRIPT_DIR / "scanner_state"
ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")

DEFAULT_COINS = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "XRP",
    "DOGE",
    "SUI",
    "LINK",
    "AVAX",
    "BNB",
    "PUMP",
    "FARTCOIN",
]

TOKEN_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "HYPE": "Hyperliquid",
    "XRP": "XRP",
    "DOGE": "Dogecoin",
    "SUI": "Sui",
    "LINK": "Chainlink",
    "AVAX": "Avalanche",
    "BNB": "BNB",
    "PUMP": "Pump.fun",
    "FARTCOIN": "Fartcoin",
}

@dataclass
class ScannerConfig:
    wallet_file: Path = DEFAULT_WALLET_FILE
    candidate_file: Path = DEFAULT_CANDIDATE_FILE
    state_dir: Path = DEFAULT_STATE_DIR
    timeout_seconds: int = 20
    pause_seconds: float = 0.20
    max_recent_trade_coins: int = 12
    max_candidates: int = 160
    selected_wallets: int = 50
    min_account_value_usd: float = 1000.0
    min_open_value_usd: float = 250.0
    coins: List[str] = None  # type: ignore


def log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


def clean_coin(coin: str) -> str:
    return str(coin or "").replace("@", "").strip().upper()


def short_wallet(wallet: str) -> str:
    return f"{wallet[:6]}…{wallet[-4:]}" if len(wallet) >= 12 else wallet


def is_wallet(value: str) -> bool:
    value = value.strip()
    return value.startswith("0x") and len(value) == 42 and bool(ADDRESS_RE.fullmatch(value))


def hl_post(payload: Dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HL_INFO_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "CopycatLocalScanner/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_addresses(path: Path) -> List[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    found: List[str] = []
    seen: Set[str] = set()
    for raw in ADDRESS_RE.findall(text):
        wallet = raw.lower()
        if is_wallet(wallet) and wallet not in seen:
            seen.add(wallet)
            found.append(wallet)
    return found


def write_address_file(path: Path, wallets: Iterable[str], header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [header.rstrip(), ""]
    for wallet in wallets:
        if is_wallet(wallet):
            lines.append(wallet.lower())
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def get_mids(timeout: int) -> Dict[str, float]:
    try:
        raw = hl_post({"type": "allMids"}, timeout)
        if isinstance(raw, dict):
            return {clean_coin(k): safe_float(v) for k, v in raw.items() if clean_coin(k)}
    except Exception as exc:
        log(f"Warning: allMids failed: {exc}")
    return {}


def discover_recent_trade_wallets(coins: List[str], timeout: int, pause: float) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    discovered: Dict[str, Dict[str, Any]] = {}
    trades_out: List[Dict[str, Any]] = []
    for coin in coins:
        coin = clean_coin(coin)
        if not coin:
            continue
        try:
            raw = hl_post({"type": "recentTrades", "coin": coin}, timeout)
            if not isinstance(raw, list):
                log(f"{coin}: recentTrades returned no list")
                continue
            log(f"{coin}: scanned {len(raw)} recent trades")
            for trade in raw:
                if not isinstance(trade, dict):
                    continue
                trade_text = json.dumps(trade, separators=(",", ":"), ensure_ascii=False)
                wallets = [w.lower() for w in ADDRESS_RE.findall(trade_text)]
                if not wallets:
                    continue
                px = safe_float(trade.get("px"))
                sz = abs(safe_float(trade.get("sz")))
                value = px * sz if px and sz else 0.0
                ts = int(safe_float(trade.get("time"), time.time() * 1000))
                trades_out.append({"coin": coin, "time": ts, "px": px, "sz": sz, "value_usd": value, "wallets": wallets})
                for wallet in wallets:
                    rec = discovered.setdefault(
                        wallet,
                        {
                            "wallet": wallet,
                            "recent_trade_count": 0,
                            "recent_trade_value_usd": 0.0,
                            "coins_seen": {},
                            "first_seen_source": "recentTrades",
                        },
                    )
                    rec["recent_trade_count"] += 1
                    rec["recent_trade_value_usd"] += value
                    rec["coins_seen"][coin] = rec["coins_seen"].get(coin, 0) + 1
        except urllib.error.HTTPError as exc:
            log(f"{coin}: recentTrades HTTP {exc.code}")
        except Exception as exc:
            log(f"{coin}: recentTrades warning: {exc}")
        time.sleep(pause)
    return discovered, trades_out


def get_state(wallet: str, timeout: int) -> Optional[Dict[str, Any]]:
    try:
        raw = hl_post({"type": "clearinghouseState", "user": wallet}, timeout)
        return raw if isinstance(raw, dict) else None
    except urllib.error.HTTPError as exc:
        log(f"{short_wallet(wallet)}: state HTTP {exc.code}")
    except Exception as exc:
        log(f"{short_wallet(wallet)}: state warning: {exc}")
    return None


def summarize_state(wallet: str, state: Dict[str, Any], mids: Dict[str, float], discovery: Dict[str, Any]) -> Dict[str, Any]:
    margin = state.get("marginSummary") or {}
    cross = state.get("crossMarginSummary") or {}
    account_value = safe_float(margin.get("accountValue") or cross.get("accountValue"))
    withdrawable = safe_float(state.get("withdrawable"))
    positions = []
    open_value = 0.0
    net_value = 0.0
    unrealized_pnl = 0.0
    coins = set()
    for row in state.get("assetPositions") or []:
        pos = row.get("position") if isinstance(row, dict) else None
        if not isinstance(pos, dict):
            continue
        coin = clean_coin(pos.get("coin"))
        szi = safe_float(pos.get("szi"))
        if not coin or abs(szi) <= 0:
            continue
        entry_px = safe_float(pos.get("entryPx"))
        mark = mids.get(coin) or safe_float(pos.get("markPx")) or entry_px
        notional = abs(szi) * mark if mark else safe_float(pos.get("positionValue"))
        signed_notional = szi * mark if mark else 0.0
        pnl = safe_float(pos.get("unrealizedPnl"))
        lev = pos.get("leverage") if isinstance(pos.get("leverage"), dict) else {}
        positions.append({
            "coin": coin,
            "szi": szi,
            "side": "long" if szi > 0 else "short",
            "mark_px": mark,
            "notional_usd": notional,
            "signed_notional_usd": signed_notional,
            "unrealized_pnl_usd": pnl,
            "leverage_type": lev.get("type"),
            "leverage_value": safe_float(lev.get("value")),
        })
        open_value += abs(notional)
        net_value += signed_notional
        unrealized_pnl += pnl
        coins.add(coin)
    recent_count = int(discovery.get("recent_trade_count") or 0)
    recent_value = safe_float(discovery.get("recent_trade_value_usd"))
    coins_seen = discovery.get("coins_seen") if isinstance(discovery.get("coins_seen"), dict) else {}
    trade_diversity = len(coins_seen)
    position_diversity = len(coins)
    gross_leverage = open_value / account_value if account_value > 0 else 0.0

    account_score = math.log10(max(account_value, 0) + 1) * 16
    open_score = math.log10(max(open_value, 0) + 1) * 18
    activity_score = min(recent_count, 40) * 1.2 + math.log10(max(recent_value, 0) + 1) * 3
    pnl_score = max(-20, min(25, unrealized_pnl / 2500.0))
    diversity_score = min(20, trade_diversity * 3 + position_diversity * 2)
    risk_penalty = 0.0
    if account_value < 1000:
        risk_penalty += 20
    if open_value < 250:
        risk_penalty += 10
    if gross_leverage > 8:
        risk_penalty += min(25, (gross_leverage - 8) * 4)
    score = account_score + open_score + activity_score + pnl_score + diversity_score - risk_penalty

    reason_bits = []
    if account_value:
        reason_bits.append(f"${account_value:,.0f} account")
    if open_value:
        reason_bits.append(f"${open_value:,.0f} open")
    if recent_count:
        reason_bits.append(f"{recent_count} recent trade hits")
    if unrealized_pnl:
        reason_bits.append(f"${unrealized_pnl:,.0f} uPnL")
    if gross_leverage:
        reason_bits.append(f"{gross_leverage:.2f}x gross lev")

    return {
        "wallet": wallet,
        "short_wallet": short_wallet(wallet),
        "score": round(score, 3),
        "account_value_usd": round(account_value, 2),
        "withdrawable_usd": round(withdrawable, 2),
        "open_position_value_usd": round(open_value, 2),
        "net_position_value_usd": round(net_value, 2),
        "gross_leverage": round(gross_leverage, 4),
        "unrealized_pnl_usd": round(unrealized_pnl, 2),
        "active_positions": len(positions),
        "position_coins": sorted(coins),
        "recent_trade_count": recent_count,
        "recent_trade_value_usd": round(recent_value, 2),
        "recent_trade_coins": sorted(coins_seen.keys()),
        "positions": sorted(positions, key=lambda p: abs(p.get("notional_usd", 0)), reverse=True)[:12],
        "reason": " · ".join(reason_bits) if reason_bits else "low visible activity",
        "eligible": account_value >= 1000 and (open_value >= 250 or recent_count > 0),
    }


def load_previous_candidates(state_dir: Path) -> List[str]:
    path = state_dir / "candidates.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return [str(w).lower() for w in raw.get("wallets", []) if is_wallet(str(w).lower())]
    except Exception:
        return []
    return []


def merge_candidates(*groups: Iterable[str], limit: int) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for group in groups:
        for raw in group:
            wallet = str(raw).strip().lower()
            if is_wallet(wallet) and wallet not in seen:
                seen.add(wallet)
                out.append(wallet)
                if len(out) >= limit:
                    return out
    return out


def run_scan(config: ScannerConfig, update_wallets: bool = False) -> Dict[str, Any]:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    coins = (config.coins or DEFAULT_COINS)[: config.max_recent_trade_coins]
    log(f"Scanner coins: {', '.join(coins)}")
    log("Discovering recent trader wallets from Hyperliquid recentTrades")
    discovered, recent_trades = discover_recent_trade_wallets(coins, config.timeout_seconds, config.pause_seconds)
    discovered_wallets = list(discovered.keys())

    existing_wallets = read_addresses(config.wallet_file)
    local_candidates = read_addresses(config.candidate_file)
    previous_candidates = load_previous_candidates(config.state_dir)
    candidates = merge_candidates(existing_wallets, discovered_wallets, local_candidates, previous_candidates, limit=config.max_candidates)
    log(f"Candidate wallet pool: {len(candidates)} ({len(discovered_wallets)} discovered from recentTrades)")

    mids = get_mids(config.timeout_seconds)
    rows: List[Dict[str, Any]] = []
    errors = 0
    for idx, wallet in enumerate(candidates, 1):
        if idx == 1 or idx % 10 == 0 or idx == len(candidates):
            log(f"Scoring wallet {idx}/{len(candidates)}")
        state = get_state(wallet, config.timeout_seconds)
        if not state:
            errors += 1
            time.sleep(config.pause_seconds)
            continue
        rows.append(summarize_state(wallet, state, mids, discovered.get(wallet, {})))
        time.sleep(config.pause_seconds)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    eligible = [r for r in rows if r.get("eligible")]
    selected_rows = (eligible or rows)[: config.selected_wallets]
    selected_wallets = [r["wallet"] for r in selected_rows]

    now_ms = int(time.time() * 1000)
    result = {
        "status": "ok" if rows else "degraded",
        "source": "local_hyperliquid_recent_trades_scanner",
        "updated_at_ms": now_ms,
        "coins_scanned": coins,
        "recent_trades_seen": len(recent_trades),
        "wallets_discovered_from_recent_trades": len(discovered_wallets),
        "candidate_wallets_scored": len(rows),
        "candidate_wallet_errors": errors,
        "selected_wallet_count": len(selected_wallets),
        "selected_wallets": selected_wallets,
        "top_rows": selected_rows,
        "all_rows": rows[:200],
        "method_note": "Scanner v1 discovers recent trader addresses from public recentTrades users, then scores visible live wallet state. It is not a full historical profit audit yet.",
    }
    (config.state_dir / "scanner_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (config.state_dir / "top_wallets.txt").write_text("\n".join(selected_wallets) + "\n", encoding="utf-8")
    all_candidates = merge_candidates(discovered_wallets, candidates, limit=1000)
    (config.state_dir / "candidates.json").write_text(json.dumps({"updated_at_ms": now_ms, "wallets": all_candidates}, indent=2), encoding="utf-8")
    write_address_file(config.candidate_file, all_candidates, "# Copycat scanner candidate pool. Auto-refreshed by scan_wallet_candidates.py.")

    log(f"Selected {len(selected_wallets)} wallet(s). Results: {config.state_dir / 'scanner_results.json'}")
    if update_wallets:
        backup = config.wallet_file.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.txt")
        if config.wallet_file.exists():
            backup.write_text(config.wallet_file.read_text(encoding="utf-8"), encoding="utf-8")
            log(f"Backed up old wallet file to {backup}")
        header = "# Copycat selected wallets. Auto-updated by local scanner v1.\n# Not a verified all-Hyperliquid top-50 profit claim."
        write_address_file(config.wallet_file, selected_wallets, header)
        log(f"Updated {config.wallet_file} with {len(selected_wallets)} selected wallet(s)")
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Copycat local wallet scanner v1")
    p.add_argument("--update-wallets", action="store_true", help="Replace wallets.txt with selected scanner top wallets")
    p.add_argument("--max-candidates", type=int, default=int(os.getenv("SCANNER_MAX_CANDIDATES", "160")))
    p.add_argument("--selected-wallets", type=int, default=int(os.getenv("SCANNER_SELECTED_WALLETS", "50")))
    p.add_argument("--coins", default=os.getenv("SCANNER_COINS", ",".join(DEFAULT_COINS)))
    p.add_argument("--timeout", type=int, default=int(os.getenv("SCANNER_TIMEOUT_SECONDS", "20")))
    p.add_argument("--pause", type=float, default=float(os.getenv("SCANNER_PAUSE_SECONDS", "0.20")))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    coins = [clean_coin(c) for c in args.coins.split(",") if clean_coin(c)]
    config = ScannerConfig(
        coins=coins,
        max_candidates=max(10, args.max_candidates),
        selected_wallets=max(1, min(50, args.selected_wallets)),
        timeout_seconds=max(5, args.timeout),
        pause_seconds=max(0.05, args.pause),
    )
    try:
        log("Copycat local wallet scanner starting")
        log(f"Update wallets.txt: {args.update_wallets}")
        result = run_scan(config, update_wallets=args.update_wallets)
        log(f"Done: {result['selected_wallet_count']} selected, {result['candidate_wallets_scored']} scored")
        return 0 if result.get("status") == "ok" else 2
    except KeyboardInterrupt:
        log("Stopped")
        return 130
    except Exception as exc:
        log(f"ERROR: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

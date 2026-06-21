#!/usr/bin/env python3
"""
Copycat local snapshot publisher.

Runs on a laptop/PC, pulls Hyperliquid-native public data for a configured wallet list,
builds compact dashboard/API JSON snapshots, and uploads them to Cloudflare R2.

It does not use Supabase and does not store historical data locally.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover
    boto3 = None


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_FILE = SCRIPT_DIR / "publisher.env"
DEFAULT_WALLET_FILE = SCRIPT_DIR / "wallets.txt"
DEFAULT_OUT_DIR = ROOT / "copycat_snapshot_out"
HL_INFO_URL = "https://api.hyperliquid.xyz/info"


TOKEN_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "HYPE": "Hyperliquid",
    "XRP": "XRP",
    "DOGE": "Dogecoin",
    "AVAX": "Avalanche",
    "SUI": "Sui",
    "LINK": "Chainlink",
    "ADA": "Cardano",
    "BNB": "BNB",
    "TRX": "TRON",
    "BCH": "Bitcoin Cash",
    "LTC": "Litecoin",
    "NEAR": "NEAR Protocol",
    "APT": "Aptos",
    "ARB": "Arbitrum",
    "OP": "Optimism",
    "TIA": "Celestia",
    "WLD": "Worldcoin",
    "PEPE": "Pepe",
    "FET": "Artificial Superintelligence Alliance",
    "INJ": "Injective",
    "SEI": "Sei",
    "MATIC": "Polygon",
    "POL": "Polygon",
    "ZEC": "Zcash",
    "XMR": "Monero",
}


@dataclass
class Config:
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str = "copycat-snapshots"
    r2_endpoint_url: Optional[str] = None
    r2_public_url: Optional[str] = None
    interval_seconds: int = 60
    max_wallets: int = 50
    fill_lookback_minutes: int = 60
    request_timeout_seconds: int = 20
    local_only: bool = False
    upload: bool = True
    out_dir: Path = DEFAULT_OUT_DIR
    wallet_file: Path = DEFAULT_WALLET_FILE


def log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except Exception:
        return default


def clean_r2_account_id(value: str) -> str:
    """Accept either a bare Cloudflare account id or a copied R2 endpoint URL."""
    value = (value or "").strip().strip('"').strip("'")
    value = value.replace('https://', '').replace('http://', '')
    value = value.split('/')[0]
    value = value.replace('.r2.cloudflarestorage.com', '')
    value = value.strip().strip('.')
    return value


def clean_r2_endpoint_url(value: str, account_id: str) -> str | None:
    value = (value or "").strip().strip('"').strip("'")
    if value:
        value = value.replace('https://https://', 'https://').replace('http://http://', 'http://')
        value = value.replace('https:/', 'https://').replace('http:/', 'http://')
        value = value.rstrip('/')
        if '.r2.cloudflarestorage.com' in value:
            value = value.split('.r2.cloudflarestorage.com', 1)[0] + '.r2.cloudflarestorage.com'
        return value
    account_id = clean_r2_account_id(account_id)
    if account_id:
        return f"https://{account_id}.r2.cloudflarestorage.com"
    return None


def load_config() -> Config:
    env_file = Path(os.getenv("COPYCAT_PUBLISHER_ENV", str(DEFAULT_ENV_FILE)))
    load_env_file(env_file)
    account_id = clean_r2_account_id(os.getenv("R2_ACCOUNT_ID", ""))
    endpoint = clean_r2_endpoint_url(os.getenv("R2_ENDPOINT_URL", ""), account_id)
    out_dir = Path(os.getenv("SNAPSHOT_OUT_DIR", str(DEFAULT_OUT_DIR))).expanduser()
    wallet_file = Path(os.getenv("COPYCAT_WALLET_FILE", str(DEFAULT_WALLET_FILE))).expanduser()
    return Config(
        r2_account_id=account_id,
        r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        r2_bucket=os.getenv("R2_BUCKET", "copycat-snapshots").strip(),
        r2_endpoint_url=endpoint,
        r2_public_url=os.getenv("R2_PUBLIC_URL", "").strip() or None,
        interval_seconds=max(15, env_int("PUBLISH_INTERVAL_SECONDS", 60)),
        max_wallets=max(1, env_int("COPYCAT_MAX_WALLETS", 50)),
        fill_lookback_minutes=max(5, env_int("FILL_LOOKBACK_MINUTES", 60)),
        request_timeout_seconds=max(5, env_int("REQUEST_TIMEOUT_SECONDS", 20)),
        local_only=env_bool("LOCAL_ONLY", False),
        upload=not env_bool("NO_UPLOAD", False),
        out_dir=out_dir,
        wallet_file=wallet_file,
    )


def is_wallet(value: str) -> bool:
    value = value.strip()
    return value.startswith("0x") and len(value) == 42 and all(c in "0123456789abcdefABCDEFx" for c in value)


def load_wallets(path: Path, max_wallets: int) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Wallet file not found: {path}")
    seen = set()
    wallets: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        wallet = line.lower()
        if is_wallet(wallet) and wallet not in seen:
            seen.add(wallet)
            wallets.append(wallet)
        if len(wallets) >= max_wallets:
            break
    if not wallets:
        raise RuntimeError(f"No valid wallet addresses found in {path}")
    return wallets


def short_wallet(wallet: str) -> str:
    return f"{wallet[:6]}…{wallet[-4:]}" if len(wallet) >= 12 else wallet


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clean_coin(coin: str) -> str:
    return str(coin or "").replace("@", "").strip()


def hl_post(payload: Dict[str, Any], timeout: int) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        HL_INFO_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "CopycatSnapshotPublisher/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_mids(timeout: int) -> Dict[str, float]:
    try:
        raw = hl_post({"type": "allMids"}, timeout)
        if isinstance(raw, dict):
            return {clean_coin(k): safe_float(v) for k, v in raw.items() if clean_coin(k)}
    except Exception as exc:
        log(f"Warning: could not fetch allMids: {exc}")
    return {}


def get_meta(timeout: int) -> Dict[str, Any]:
    try:
        raw = hl_post({"type": "meta"}, timeout)
        universe = raw.get("universe", []) if isinstance(raw, dict) else []
        return {clean_coin(row.get("name")): row for row in universe if isinstance(row, dict) and row.get("name")}
    except Exception as exc:
        log(f"Warning: could not fetch meta: {exc}")
    return {}


def get_state(wallet: str, timeout: int) -> Optional[Dict[str, Any]]:
    try:
        raw = hl_post({"type": "clearinghouseState", "user": wallet}, timeout)
        return raw if isinstance(raw, dict) else None
    except urllib.error.HTTPError as exc:
        log(f"Wallet {short_wallet(wallet)} state HTTP error: {exc.code}")
    except Exception as exc:
        log(f"Wallet {short_wallet(wallet)} state error: {exc}")
    return None


def get_fills(wallet: str, start_ms: int, timeout: int) -> List[Dict[str, Any]]:
    try:
        raw = hl_post({"type": "userFillsByTime", "user": wallet, "startTime": start_ms}, timeout)
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception as exc:
        log(f"Wallet {short_wallet(wallet)} fills warning: {exc}")
    return []


def position_side(szi: float) -> str:
    if szi > 0:
        return "long"
    if szi < 0:
        return "short"
    return "flat"


def confidence(abs_signal: float, gross: float, wallets_involved: int) -> str:
    if abs_signal >= 0.75 and gross >= 50000 and wallets_involved >= 2:
        return "High"
    if abs_signal >= 0.4 and gross >= 10000:
        return "Medium"
    return "Low"


def fill_direction(fill: Dict[str, Any]) -> str:
    return str(fill.get("dir") or fill.get("direction") or fill.get("side") or "Trade")


def fill_is_bullish(fill: Dict[str, Any]) -> bool:
    direction = fill_direction(fill).lower()
    side = str(fill.get("side") or "").upper()
    if "open long" in direction or "close short" in direction:
        return True
    if "open short" in direction or "close long" in direction:
        return False
    return side == "B"


def build_snapshots(wallets: List[str], config: Config) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    now_ms = int(time.time() * 1000)
    mids = get_mids(config.request_timeout_seconds)
    meta = get_meta(config.request_timeout_seconds)
    states: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []
    start_ms = now_ms - config.fill_lookback_minutes * 60 * 1000

    log(f"Fetching Hyperliquid state for {len(wallets)} wallet(s)")
    for idx, wallet in enumerate(wallets, 1):
        state = get_state(wallet, config.request_timeout_seconds)
        if state:
            state["_wallet"] = wallet
            states.append(state)
        fills = get_fills(wallet, start_ms, config.request_timeout_seconds)
        for fill in fills:
            coin = clean_coin(fill.get("coin"))
            px = safe_float(fill.get("px"))
            size = abs(safe_float(fill.get("sz")))
            value = round(px * size, 2) if px and size else 0.0
            direction = fill_direction(fill)
            ts_ms = safe_int(fill.get("time"), now_ms)
            orders.append(
                {
                    "ts_ms": ts_ms,
                    "wallet": wallet,
                    "wallet_label": short_wallet(wallet),
                    "coin": coin,
                    "side": direction,
                    "delta_value_usd": value,
                    "position_value_usd": value,
                    "source": "local_hyperliquid",
                }
            )
        time.sleep(0.15)
        if idx % 10 == 0:
            log(f"Fetched {idx}/{len(wallets)} wallet(s)")

    by_coin: Dict[str, Dict[str, Any]] = {}
    wallet_rows: List[Dict[str, Any]] = []
    tracked_account_value = 0.0
    largest_account_value = 0.0
    open_value_total = 0.0
    open_positions = 0

    for state in states:
        wallet = state.get("_wallet", "")
        margin = state.get("marginSummary") or state.get("crossMarginSummary") or {}
        account_value = safe_float(margin.get("accountValue"))
        tracked_account_value += account_value
        largest_account_value = max(largest_account_value, account_value)
        wallet_open = 0.0
        wallet_position_count = 0
        for item in state.get("assetPositions") or []:
            pos = item.get("position") if isinstance(item, dict) else None
            if not isinstance(pos, dict):
                continue
            coin = clean_coin(pos.get("coin"))
            if not coin:
                continue
            szi = safe_float(pos.get("szi") or pos.get("sz"))
            side = position_side(szi)
            if side == "flat":
                continue
            value = abs(safe_float(pos.get("positionValue")))
            if not value:
                mark = mids.get(coin, safe_float(pos.get("markPx")))
                value = abs(szi) * mark
            if value <= 0:
                continue
            row = by_coin.setdefault(
                coin,
                {
                    "coin": coin,
                    "long_value": 0.0,
                    "short_value": 0.0,
                    "wallets_long": set(),
                    "wallets_short": set(),
                },
            )
            if side == "long":
                row["long_value"] += value
                row["wallets_long"].add(wallet)
            else:
                row["short_value"] += value
                row["wallets_short"].add(wallet)
            wallet_open += value
            open_value_total += value
            wallet_position_count += 1
            open_positions += 1
        wallet_rows.append(
            {
                "wallet": wallet,
                "wallet_label": short_wallet(wallet),
                "account_value_usd": round(account_value, 2),
                "open_position_value_usd": round(wallet_open, 2),
                "open_positions": wallet_position_count,
                "source": "local_hyperliquid",
            }
        )

    signals: List[Dict[str, Any]] = []
    for coin, row in by_coin.items():
        long_v = row["long_value"]
        short_v = row["short_value"]
        gross = long_v + short_v
        if gross <= 0:
            continue
        sig = (long_v - short_v) / gross
        wallets_long = len(row["wallets_long"])
        wallets_short = len(row["wallets_short"])
        signals.append(
            {
                "coin": coin,
                "name": TOKEN_NAMES.get(coin, coin),
                "price_usd": mids.get(coin),
                "ts_ms": now_ms,
                "signal": round(sig, 6),
                "confidence": confidence(abs(sig), gross, wallets_long + wallets_short),
                "wallets_long": wallets_long,
                "wallets_short": wallets_short,
                "value_long_usd": round(long_v, 2),
                "value_short_usd": round(short_v, 2),
                "net_value_usd": round(long_v - short_v, 2),
                "gross_value_usd": round(gross, 2),
                "value_long_pct_total": round(long_v / open_value_total, 6) if open_value_total else 0,
                "value_short_pct_total": round(short_v / open_value_total, 6) if open_value_total else 0,
                "live_state": True,
                "source": "local_hyperliquid",
            }
        )
    signals.sort(key=lambda r: (abs(r["signal"]) * r.get("gross_value_usd", 0), r.get("gross_value_usd", 0)), reverse=True)

    targets: List[Dict[str, Any]] = []
    total_gross = sum(s.get("gross_value_usd", 0.0) for s in signals) or 1.0
    for s in signals:
        gross = s.get("gross_value_usd", 0.0)
        weight = gross / total_gross
        direction = "long" if s["signal"] >= 0 else "short"
        targets.append(
            {
                "ts_ms": now_ms,
                "coin": s["coin"],
                "target_weight": round(weight, 6),
                "index_weight": round(weight if direction == "long" else -weight, 6),
                "direction": direction,
            }
        )

    flow_by_coin: Dict[str, Dict[str, Any]] = {}
    for order in orders:
        coin = clean_coin(order.get("coin"))
        value = safe_float(order.get("delta_value_usd"))
        row = flow_by_coin.setdefault(
            coin,
            {"coin": coin, "net_buyer_count": 0, "bullish_flow_usd": 0.0, "bearish_flow_usd": 0.0, "net_value_flow_usd": 0.0},
        )
        bullish = str(order.get("side", "")).lower().find("open long") >= 0 or str(order.get("side", "")).lower().find("close short") >= 0
        if not bullish and (str(order.get("side", "")).lower().find("open short") >= 0 or str(order.get("side", "")).lower().find("close long") >= 0):
            bullish = False
        elif str(order.get("side", "")).lower() in {"b", "buy"}:
            bullish = True
        if bullish:
            row["bullish_flow_usd"] += value
            row["net_value_flow_usd"] += value
            row["net_buyer_count"] += 1
        else:
            row["bearish_flow_usd"] += value
            row["net_value_flow_usd"] -= value
            row["net_buyer_count"] -= 1
    flow = list(flow_by_coin.values())
    for r in flow:
        for k in ["bullish_flow_usd", "bearish_flow_usd", "net_value_flow_usd"]:
            r[k] = round(r[k], 2)
    flow.sort(key=lambda r: abs(r.get("net_value_flow_usd", 0)) + r.get("bullish_flow_usd", 0) + r.get("bearish_flow_usd", 0), reverse=True)

    orders.sort(key=lambda r: safe_int(r.get("ts_ms")), reverse=True)
    orders = orders[:50]

    data_status = "healthy" if states else "degraded"
    data_msg = "Local Hyperliquid snapshot publisher active" if states else "No wallet states fetched; check wallets.txt and network"
    summary = {
        "latest_signal_ts_ms": now_ms,
        "latest_position_ts_ms": now_ms,
        "latest_live_state_ts_ms": now_ms,
        "live_state_active": bool(states),
        "live_coverage_mode": "local_snapshot",
        "live_wallets": len(states),
        "snapshot_wallets": 0,
        "qualified_wallets": len(wallets),
        "tracked_account_value_usd": round(tracked_account_value, 2),
        "largest_account_value_usd": round(largest_account_value, 2),
        "tracked_open_position_value_usd": round(open_value_total, 2),
        "open_positions": open_positions,
        "assets_with_signals": len(signals),
        "markets_monitored": len(mids) or len(meta),
        "data_quality_status": data_status,
        "data_quality_age_seconds": 0,
        "data_quality_message": data_msg,
        "snapshot_mode": True,
        "snapshot_source": "local_hyperliquid_to_r2",
    }

    insights: List[Dict[str, Any]] = []
    if signals:
        top_signal = signals[0]
        pct = round(abs(safe_float(top_signal.get("signal"))) * 100)
        side = "Long" if safe_float(top_signal.get("signal")) >= 0 else "Short"
        insights.append({"type": "top_signal", "label": "Top conviction asset", "coin": top_signal["coin"], "detail": f"{pct}% {side} · {top_signal.get('confidence')}", "row": top_signal})
        largest = max(signals, key=lambda r: r.get("gross_value_usd", 0))
        insights.append({"type": "largest_exposure", "label": "Largest current exposure", "coin": largest["coin"], "detail": f"${largest.get('gross_value_usd',0):,.0f} gross exposure", "row": largest})
    if flow:
        acc = max(flow, key=lambda r: r.get("net_value_flow_usd", 0))
        dist = min(flow, key=lambda r: r.get("net_value_flow_usd", 0))
        if acc.get("net_value_flow_usd", 0) > 0:
            insights.append({"type": "accumulation", "label": "Recent accumulation", "coin": acc["coin"], "detail": f"Net flow ${acc.get('net_value_flow_usd', 0):,.0f}", "row": acc})
        if dist.get("net_value_flow_usd", 0) < 0:
            insights.append({"type": "distribution", "label": "Recent distribution", "coin": dist["coin"], "detail": f"Net flow ${dist.get('net_value_flow_usd', 0):,.0f}", "row": dist})
    leverage = round(open_value_total / tracked_account_value, 2) if tracked_account_value else 0.0
    insights.append({"type": "gross_leverage", "label": "Gross leverage", "coin": None, "detail": f"{leverage:.2f}x across tracked wallets", "row": {"gross_leverage": leverage}})

    feed = {
        "summary": summary,
        "signals": signals[:80],
        "targets": targets[:80],
        "flow": flow[:80],
        "orders": orders,
        "insights": insights[:8],
        "server_time_ms": now_ms,
        "cache_ttl_ms": config.interval_seconds * 1000,
        "public_readonly": True,
        "snapshot_generated_at_ms": now_ms,
        "snapshot_notice": "Generated by local Copycat Hyperliquid publisher. No Supabase required.",
    }
    tick = {
        "summary": summary,
        "orders": orders[:40],
        "server_time_ms": now_ms,
        "cache_ttl_ms": min(config.interval_seconds, 30) * 1000,
        "public_readonly": True,
        "snapshot_mode": True,
        "snapshot_generated_at_ms": now_ms,
    }
    leaderboard = {
        "status": "ok",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "wallet_count": len(wallet_rows),
        "rows": sorted(wallet_rows, key=lambda r: (r.get("account_value_usd", 0), r.get("open_position_value_usd", 0)), reverse=True)[:50],
    }
    token_screener = {
        "status": "ok",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "rows": [
            {
                "coin": s["coin"],
                "name": s.get("name") or s["coin"],
                "price_usd": s.get("price_usd"),
                "signal": s["signal"],
                "signal_label": f"{round(abs(s['signal']) * 100)}% {'Long' if s['signal'] >= 0 else 'Short'}",
                "confidence": s["confidence"],
                "gross_value_usd": s.get("gross_value_usd", 0),
                "net_value_usd": s.get("net_value_usd", 0),
                "wallets_long": s.get("wallets_long", 0),
                "wallets_short": s.get("wallets_short", 0),
            }
            for s in signals[:100]
        ],
    }
    coverage = {
        "status": "ok" if states else "degraded",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "wallets_configured": len(wallets),
        "wallets_fetched": len(states),
        "assets_with_signals": len(signals),
        "recent_orders": len(orders),
        "storage_mode": "r2_snapshot_overwrite",
        "supabase_required": False,
        "historical_backfill_enabled": False,
        "message": data_msg,
    }
    platform_health = {
        "status": "ok" if states else "degraded",
        "service": "copycat-snapshot-publisher",
        "updated_at_ms": now_ms,
        "frontend": "cloudflare_pages",
        "data_delivery": "cloudflare_r2_snapshots",
        "database_required_for_dashboard": False,
        "wallets": len(states),
    }
    status = {
        "status": "ok" if states else "degraded",
        "product": "Copycat Data API",
        "version": "snapshot-v1",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "tracked_active_wallets": len(states),
        "assets_with_signals": len(signals),
        "snapshot_mode": True,
    }
    performance_index = {
        "status": "ok",
        "source": "local_snapshot_placeholder",
        "updated_at_ms": now_ms,
        "points": [
            {"ts_ms": now_ms - 3 * 3600_000, "copycat": 100.0, "btc": 100.0, "eth": 100.0},
            {"ts_ms": now_ms - 2 * 3600_000, "copycat": 100.0, "btc": 100.0, "eth": 100.0},
            {"ts_ms": now_ms - 1 * 3600_000, "copycat": 100.0, "btc": 100.0, "eth": 100.0},
            {"ts_ms": now_ms, "copycat": 100.0, "btc": 100.0, "eth": 100.0},
        ],
    }
    token_icons = {s["coin"]: None for s in signals[:100]}

    return {
        "dashboard-feed.json": ("application/json", feed),
        "dashboard-tick.json": ("application/json", tick),
        "performance-index.json": ("application/json", performance_index),
        "token-icons.json": ("application/json", token_icons),
        "api/leaderboard-preview.json": ("application/json", leaderboard),
        "api/token-screener-preview.json": ("application/json", token_screener),
        "api/coverage-preview.json": ("application/json", coverage),
        "api/platform-health.json": ("application/json", platform_health),
        "api/status.json": ("application/json", status),
    }


def write_local(out_dir: Path, snapshots: Dict[str, Tuple[str, Dict[str, Any]]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, (_ctype, payload) in snapshots.items():
        path = out_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    log(f"Wrote local snapshots to {out_dir}")


def upload_r2(config: Config, snapshots: Dict[str, Tuple[str, Dict[str, Any]]]) -> None:
    if not config.upload or config.local_only:
        log("Upload skipped because LOCAL_ONLY/NO_UPLOAD is set")
        return
    if boto3 is None:
        raise RuntimeError("boto3 is not installed. Run install_snapshot_publisher.cmd first.")
    if not (config.r2_access_key_id and config.r2_secret_access_key and config.r2_endpoint_url and config.r2_bucket):
        raise RuntimeError("Missing R2 credentials. Fill scripts/local_snapshot_publisher/publisher.env first.")
    log(f"Uploading snapshots to R2 endpoint: {config.r2_endpoint_url}")
    s3 = boto3.client(
        "s3",
        endpoint_url=config.r2_endpoint_url,
        aws_access_key_id=config.r2_access_key_id,
        aws_secret_access_key=config.r2_secret_access_key,
        region_name="auto",
    )
    for key, (content_type, payload) in snapshots.items():
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        s3.put_object(
            Bucket=config.r2_bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="public, max-age=20, s-maxage=20",
        )
    log(f"Uploaded {len(snapshots)} snapshot file(s) to R2 bucket {config.r2_bucket}")


def once(config: Config) -> None:
    wallets = load_wallets(config.wallet_file, config.max_wallets)
    snapshots = build_snapshots(wallets, config)
    write_local(config.out_dir, snapshots)
    upload_r2(config, snapshots)
    public_url = (config.r2_public_url or "").rstrip("/")
    if public_url:
        log(f"Dashboard snapshot URL: {public_url}/dashboard-feed.json")


def main() -> int:
    config = load_config()
    log("Copycat local snapshot publisher starting")
    log(f"Wallet file: {config.wallet_file}")
    log(f"Interval: {config.interval_seconds}s | max wallets: {config.max_wallets} | local only: {config.local_only}")
    run_once = "--once" in sys.argv
    while True:
        try:
            once(config)
        except KeyboardInterrupt:
            log("Stopped")
            return 0
        except Exception as exc:
            log(f"ERROR: {exc}")
            traceback.print_exc()
        if run_once:
            return 0
        time.sleep(config.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

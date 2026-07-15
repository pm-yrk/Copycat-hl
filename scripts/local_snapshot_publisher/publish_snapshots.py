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
from copy import deepcopy
import urllib.request
import urllib.error
import concurrent.futures
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
    request_pause_seconds: float = 0.45
    state_cache_max_age_seconds: int = 6 * 60 * 60
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


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
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
        request_pause_seconds=max(0.15, env_float("REQUEST_PAUSE_SECONDS", 0.45)),
        state_cache_max_age_seconds=max(300, env_int("STATE_CACHE_MAX_AGE_SECONDS", 6 * 60 * 60)),
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
    return f"{wallet[:6]}â€¦{wallet[-4:]}" if len(wallet) >= 12 else wallet


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


def get_state(wallet: str, timeout: int, retries: int = 2) -> Optional[Dict[str, Any]]:
    for attempt in range(retries + 1):
        try:
            raw = hl_post({"type": "clearinghouseState", "user": wallet}, timeout)
            return raw if isinstance(raw, dict) else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                wait = 1.5 * (attempt + 1)
                log(f"Wallet {short_wallet(wallet)} state HTTP 429; retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            log(f"Wallet {short_wallet(wallet)} state HTTP error: {exc.code}")
        except Exception as exc:
            log(f"Wallet {short_wallet(wallet)} state error: {exc}")
            break
    return None


def get_fills(wallet: str, start_ms: int, timeout: int, retries: int = 1) -> List[Dict[str, Any]]:
    for attempt in range(retries + 1):
        try:
            raw = hl_post({"type": "userFillsByTime", "user": wallet, "startTime": start_ms}, timeout)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
            return []
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                wait = 1.5 * (attempt + 1)
                log(f"Wallet {short_wallet(wallet)} fills HTTP 429; retrying in {wait:.1f}s")
                time.sleep(wait)
                continue
            log(f"Wallet {short_wallet(wallet)} fills warning: HTTP Error {exc.code}: {exc.reason}")
        except Exception as exc:
            log(f"Wallet {short_wallet(wallet)} fills warning: {exc}")
            break
    return []


def wallet_cache_path() -> Path:
    return SCRIPT_DIR / "scanner_state" / "wallet_state_cache.json"


def load_wallet_state_cache() -> Dict[str, Any]:
    path = wallet_cache_path()
    if not path.exists():
        return {"states": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("states", {})
            return raw
    except Exception:
        pass
    return {"states": {}}


def save_wallet_state_cache(cache: Dict[str, Any]) -> None:
    try:
        path = wallet_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log(f"Warning: could not save wallet cache: {exc}")


def cached_state_for_wallet(cache: Dict[str, Any], wallet: str, now_ms: int, max_age_seconds: int) -> Optional[Dict[str, Any]]:
    states = cache.get("states") if isinstance(cache.get("states"), dict) else {}
    item = states.get(wallet.lower()) if isinstance(states, dict) else None
    if not isinstance(item, dict):
        return None
    updated_at_ms = safe_int(item.get("updated_at_ms"))
    state = item.get("state")
    if not isinstance(state, dict) or updated_at_ms <= 0:
        return None
    age_seconds = max(0, int((now_ms - updated_at_ms) / 1000))
    if age_seconds > max_age_seconds:
        return None
    cached = deepcopy(state)
    cached["_copycat_cache_age_seconds"] = age_seconds
    return cached


def remember_wallet_state(cache: Dict[str, Any], wallet: str, state: Dict[str, Any], now_ms: int) -> None:
    states = cache.setdefault("states", {})
    if not isinstance(states, dict):
        states = {}
        cache["states"] = states
    clean_state = deepcopy(state)
    for key in ["_wallet", "_copycat_state_status", "_copycat_cache_age_seconds"]:
        clean_state.pop(key, None)
    states[wallet.lower()] = {"updated_at_ms": now_ms, "state": clean_state}


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



def read_scanner_results() -> Dict[str, Any]:
    path = SCRIPT_DIR / "scanner_state" / "scanner_results.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def build_performance_index_snapshot(now_ms: int, mids: Dict[str, float], signals: List[Dict[str, Any]], targets: List[Dict[str, Any]], config: Config) -> Dict[str, Any]:
    """Maintain a tiny from-now performance index without Supabase.

    This is a live snapshot-mode index: it starts at 100 when this local publisher
    first runs, then updates using the current value-weighted signed exposure.
    It is not a historical backfill and does not claim all-Hyperliquid ranking.
    """
    state_dir = SCRIPT_DIR / "scanner_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "performance_index_state.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(state, dict):
            state = {}
    except Exception:
        state = {}

    current_weights: List[Dict[str, Any]] = []
    rows = targets or []
    for row in rows:
        coin = clean_coin(row.get("coin"))
        if not coin or coin == "USDC":
            continue
        signed = safe_float(row.get("signed_weight"), safe_float(row.get("index_weight"), safe_float(row.get("target_weight"))))
        direction = str(row.get("direction") or ("short" if signed < 0 else "long")).lower()
        weight = abs(signed)
        if weight > 0:
            current_weights.append({"coin": coin, "weight": weight, "signed_weight": signed, "direction": direction})
    if not current_weights:
        total_gross = sum(abs(safe_float(s.get("net_value_usd"))) for s in signals) or sum(safe_float(s.get("gross_value_usd")) for s in signals) or 1.0
        for s in signals[:30]:
            coin = clean_coin(s.get("coin"))
            if not coin or coin == "USDC":
                continue
            net = safe_float(s.get("net_value_usd"), safe_float(s.get("signal")) * safe_float(s.get("gross_value_usd")))
            signed = net / total_gross if total_gross else 0.0
            if signed:
                current_weights.append({"coin": coin, "weight": abs(signed), "signed_weight": signed, "direction": "short" if signed < 0 else "long"})
    total_abs = sum(abs(safe_float(w.get("signed_weight"))) for w in current_weights) or 1.0
    for w in current_weights:
        signed = safe_float(w.get("signed_weight")) / total_abs
        w["signed_weight"] = signed
        w["weight"] = abs(signed)

    last_mids = state.get("last_mids") if isinstance(state.get("last_mids"), dict) else {}
    copycat_nav = safe_float(state.get("copycat_nav"), 100.0)
    btc_nav = safe_float(state.get("btc_nav"), 100.0)
    eth_nav = safe_float(state.get("eth_nav"), 100.0)
    spx_nav = safe_float(state.get("spx_nav"), 100.0)
    # Hyperliquid/Trade[XYZ] SP500 is shown publicly as S&P 500 on the dashboard,
    # but the Hyperliquid allMids feed currently exposes the live mid under SPX
    # with @500 also present as an alternate key.
    spx_symbol = "SPX"
    for candidate in ("SPX", "@500", "xyz:SP500", "XYZ:SP500", "SP500"):
        if safe_float(mids.get(candidate)) > 0 or safe_float(last_mids.get(candidate)) > 0:
            spx_symbol = candidate
            break
    movement = 0.0
    for w in current_weights:
        coin = str(w.get("coin"))
        prev = safe_float(last_mids.get(coin))
        cur = safe_float(mids.get(coin))
        if prev > 0 and cur > 0:
            movement += safe_float(w.get("signed_weight")) * ((cur / prev) - 1.0)
    movement = clamp(movement, -0.08, 0.08)
    copycat_nav = copycat_nav * (1.0 + movement)

    def update_benchmark(symbol: str, nav_value: float) -> float:
        prev = safe_float(last_mids.get(symbol))
        cur = safe_float(mids.get(symbol))
        if prev > 0 and cur > 0:
            return nav_value * (1.0 + clamp((cur / prev) - 1.0, -0.08, 0.08))
        return nav_value

    btc_nav = update_benchmark("BTC", btc_nav)
    eth_nav = update_benchmark("ETH", eth_nav)
    spx_nav = update_benchmark(spx_symbol, spx_nav)
    start_ts = int(state.get("start_ts_ms") or now_ms)
    points = state.get("points") if isinstance(state.get("points"), list) else []
    point = {
        "ts_ms": now_ms,
        "copycat_nav": round(copycat_nav, 6),
        "btc_nav": round(btc_nav, 6),
        "eth_nav": round(eth_nav, 6),
        "spx_nav": round(spx_nav, 6),
        "copycat_return_pct": round(copycat_nav - 100.0, 6),
        "btc_return_pct": round(btc_nav - 100.0, 6),
        "eth_return_pct": round(eth_nav - 100.0, 6),
        "spx_return_pct": round(spx_nav - 100.0, 6),
        "live": True,
    }
    if not points or int(points[-1].get("ts_ms", 0)) < now_ms - 20_000:
        points.append(point)
    else:
        points[-1] = point
    points = points[-720:]
    peak = 100.0
    max_dd = 0.0
    for p in points:
        nav = safe_float(p.get("copycat_nav"), 100.0)
        peak = max(peak, nav)
        if peak:
            max_dd = min(max_dd, (nav / peak - 1.0) * 100.0)

    next_state = {
        "start_ts_ms": start_ts,
        "latest_ts_ms": now_ms,
        "copycat_nav": copycat_nav,
        "btc_nav": btc_nav,
        "eth_nav": eth_nav,
        "spx_nav": spx_nav,
        "points": points,
        "last_mids": {k: v for k, v in mids.items() if k in {"BTC", "ETH", spx_symbol} or any(w.get("coin") == k for w in current_weights)},
    }
    try:
        path.write_text(json.dumps(next_state, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass

    return {
        "status": "ok",
        "source": "local_snapshot_index_v1",
        "spx_benchmark_symbol": spx_symbol,
        "method": "copycat_free_mode_live_signed_exposure_from_publish_time",
        "method_note": "Free-mode index starts when the local publisher runs. It uses current value-weighted signed exposure from the locally tracked wallets and is not a historical profit backfill.",
        "start_ts_ms": start_ts,
        "latest_ts_ms": now_ms,
        "copycat_nav": round(copycat_nav, 6),
        "btc_nav": round(btc_nav, 6),
        "eth_nav": round(eth_nav, 6),
        "spx_nav": round(spx_nav, 6),
        "copycat_return_pct": round(copycat_nav - 100.0, 6),
        "btc_return_pct": round(btc_nav - 100.0, 6),
        "eth_return_pct": round(eth_nav - 100.0, 6),
        "spx_return_pct": round(spx_nav - 100.0, 6),
        "max_drawdown_pct": round(max_dd, 6),
        "points_count": len(points),
        "points": points,
        "current_weights": current_weights[:20],
        "cache_ttl_ms": config.interval_seconds * 1000,
        "public_readonly": True,
        "snapshot_mode": True,
    }

# Copycat registry summary counts v1
def read_registry_summary_counts() -> Dict[str, int]:
    # Read long-running local registry counts for public dashboard summary fields.
    # This does not change wallet selection. The live publisher still tracks the
    # selected top wallet list, but dashboard summary counts can reflect the larger
    # local registry/scout universe.
    import os
    import sqlite3
    from pathlib import Path as _Path

    candidates = []
    env_path = os.environ.get("COPYCAT_WALLET_REGISTRY_DB", "").strip()
    if env_path:
        candidates.append(_Path(env_path))

    candidates.extend([
        _Path(r"C:\dev\hyper_wallet_tracker_saas_v1\copycat_wallet_registry\copycat_wallet_registry.sqlite"),
        _Path(__file__).resolve().parent / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite",
        _Path(__file__).resolve().parents[1] / "copycat_wallet_registry" / "copycat_wallet_registry.sqlite" if len(_Path(__file__).resolve().parents) > 1 else _Path("__missing__"),
    ])

    db_path = next((p for p in candidates if p.exists()), None)
    if not db_path:
        return {"registry_wallets": 0, "registry_scan_history": 0, "registry_discoveries": 0}

    def _count_table(cur, table: str) -> int:
        try:
            return int(cur.execute(f"select count(*) from {table}").fetchone()[0] or 0)
        except Exception:
            return 0

    con = None
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        return {
            "registry_wallets": _count_table(cur, "wallets"),
            "registry_scan_history": _count_table(cur, "scan_history"),
            "registry_discoveries": _count_table(cur, "discoveries"),
        }
    except Exception:
        return {"registry_wallets": 0, "registry_scan_history": 0, "registry_discoveries": 0}
    finally:
        try:
            if con is not None:
                con.close()
        except Exception:
            pass


# COPYCAT_MARKET_NARRATIVE_V1_START
MARKET_NEWS_REFRESH_MS = 5 * 60 * 1000
MARKET_NEWS_MAX_AGE_MS = 72 * 60 * 60 * 1000
MARKET_NEWS_CACHE = SCRIPT_DIR / "scanner_state" / "market_narrative_cache.json"

# Public RSS/Atom sources only. Copycat stores and displays the source name,
# headline, publication time and original link; it does not republish article bodies.
MARKET_NEWS_SOURCES = [
    {"name": "CoinDesk", "badge": "CD", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "weight": 9, "always_relevant": True},
    {"name": "Cointelegraph", "badge": "CT", "url": "https://cointelegraph.com/rss", "weight": 8, "always_relevant": True},
    {"name": "Decrypt", "badge": "D", "url": "https://decrypt.co/feed", "weight": 8, "always_relevant": True},
    {"name": "CryptoSlate", "badge": "CS", "url": "https://cryptoslate.com/feed/", "weight": 7, "always_relevant": True},
    {"name": "SEC", "badge": "SEC", "url": "https://www.sec.gov/news/pressreleases.rss", "weight": 10},
    {"name": "SEC", "badge": "SEC", "url": "https://www.sec.gov/news/speeches-statements.rss", "weight": 8},
    {"name": "Federal Reserve", "badge": "FED", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "weight": 9},
    {"name": "Federal Reserve", "badge": "FED", "url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "weight": 10},
    {"name": "CFTC", "badge": "CFTC", "url": "https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "weight": 10},
    {"name": "CFTC", "badge": "CFTC", "url": "https://www.cftc.gov/RSS/RSSENF/rssenf.xml", "weight": 9},
    {"name": "ECB", "badge": "ECB", "url": "https://www.ecb.europa.eu/rss/press.html", "weight": 9},
    {"name": "ECB", "badge": "ECB", "url": "https://www.ecb.europa.eu/rss/blog.html", "weight": 7},
    {"name": "BIS", "badge": "BIS", "url": "https://www.bis.org/doclist/all_pressrels.rss", "weight": 8},
    {"name": "FCA", "badge": "FCA", "url": "https://www.fca.org.uk/news/rss.xml", "weight": 9},
    {"name": "Ethereum Foundation", "badge": "ETH", "url": "https://blog.ethereum.org/feed.xml", "weight": 7, "always_relevant": True},
    {"name": "Kraken", "badge": "K", "url": "https://blog.kraken.com/feed", "weight": 6, "always_relevant": True},
]

MARKET_RELEVANCE_TERMS = {
    "bitcoin": 8, "btc": 7, "ethereum": 8, "ether": 7, "eth": 6,
    "crypto": 8, "cryptocurrency": 8, "digital asset": 8, "blockchain": 7,
    "stablecoin": 8, "token": 5, "defi": 7, "web3": 5, "wallet": 5,
    "exchange": 4, "custody": 6, "spot etf": 8, "etf": 6, "mining": 5,
    "hyperliquid": 9, "solana": 7, "xrp": 6, "dogecoin": 5,
    "interest rate": 6, "rate cut": 7, "rate hike": 7, "inflation": 6,
    "federal reserve": 6, "fed": 4, "monetary policy": 6, "liquidity": 6,
    "treasury": 4, "bond yield": 5, "dollar": 4, "sanction": 4,
    "market volatility": 5, "risk asset": 5, "financial stability": 5,
}

BULLISH_HEADLINE_TERMS = [
    "approve", "approval", "approved", "inflow", "inflows", "rally", "surge",
    "surges", "rise", "rises", "gain", "gains", "record high", "all-time high",
    "adoption", "launch", "launches", "partnership", "accumulation", "upgrade",
    "expansion", "milestone", "rebound", "recovers", "recovery", "resumes",
    "rate cut", "cuts rates", "easing", "regulatory clarity", "green light",
]

BEARISH_HEADLINE_TERMS = [
    "hack", "exploit", "breach", "stolen", "liquidation", "liquidations",
    "outflow", "outflows", "decline", "falls", "fall", "drops", "drop",
    "plunge", "ban", "lawsuit", "charges", "charged", "enforcement",
    "investigation", "delay", "delays", "reject", "rejected", "denied",
    "rate hike", "hikes rates", "hawkish", "sanctions", "war", "attack",
    "default", "bankrupt", "insolvency", "depeg", "outage", "halt",
    "suspend", "crackdown", "fraud", "scam", "warning",
]


def _market_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _market_tag_name(tag: str) -> str:
    return str(tag or "").split("}")[-1].lower()


def _market_child_text(node: Any, names: Iterable[str]) -> str:
    wanted = {str(name).lower() for name in names}
    for child in list(node):
        if _market_tag_name(getattr(child, "tag", "")) in wanted:
            value = "".join(child.itertext()) if hasattr(child, "itertext") else (child.text or "")
            return _market_text(value)
    return ""


def _market_item_link(node: Any) -> str:
    for child in list(node):
        if _market_tag_name(getattr(child, "tag", "")) != "link":
            continue
        href = _market_text(getattr(child, "attrib", {}).get("href"))
        rel = _market_text(getattr(child, "attrib", {}).get("rel")).lower()
        if href and rel in {"", "alternate"}:
            return href
        text = _market_text(getattr(child, "text", ""))
        if text:
            return text
    return _market_child_text(node, {"guid"})


def _market_parse_date_ms(value: str, fallback_ms: int) -> int:
    text = _market_text(value)
    if not text:
        return fallback_ms
    try:
        parsed = parsedate_to_datetime(text)
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except Exception:
        return fallback_ms


def _market_normal_title(value: str) -> str:
    text = _market_text(value).lower()
    text = re.sub(r"\s*[-|:]\s*(coindesk|cointelegraph|decrypt|cryptoslate)\s*$", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _market_title_is_duplicate(title: str, accepted: List[Dict[str, Any]]) -> bool:
    normal = _market_normal_title(title)
    if not normal:
        return True
    words = set(normal.split())
    for row in accepted:
        other = _market_normal_title(row.get("title", ""))
        if normal == other:
            return True
        other_words = set(other.split())
        if words and other_words:
            overlap = len(words & other_words) / max(1, min(len(words), len(other_words)))
            if overlap >= 0.82:
                return True
    return False


def _market_sentiment(title: str) -> Tuple[str, int]:
    text = _market_normal_title(title)
    positive = sum(1 for term in BULLISH_HEADLINE_TERMS if term in text)
    negative = sum(1 for term in BEARISH_HEADLINE_TERMS if term in text)
    score = positive - negative
    if score > 0:
        return "bullish", score
    if score < 0:
        return "bearish", score
    return "neutral", 0


def _market_relevance(title: str, source: Dict[str, Any], asset_terms: Iterable[str], now_ms: int, published_ms: int) -> float:
    text = _market_normal_title(title)
    score = float(source.get("weight") or 0)
    if source.get("always_relevant"):
        score += 8.0
    for term, weight in MARKET_RELEVANCE_TERMS.items():
        if term in text:
            score += float(weight)
    for term in asset_terms:
        clean = _market_normal_title(term)
        if clean and re.search(rf"\b{re.escape(clean)}\b", text):
            score += 5.0
    age_hours = max(0.0, (now_ms - published_ms) / 3_600_000.0)
    score += max(0.0, 18.0 - age_hours) * 0.45
    return score


def _market_fetch_source(source: Dict[str, Any], timeout: int, now_ms: int) -> Tuple[str, List[Dict[str, Any]], str]:
    request = urllib.request.Request(
        str(source["url"]),
        headers={
            "User-Agent": "CopycatMarketNarrative/1.0 paulmurrin13@gmail.com",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.6",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=max(4, min(timeout, 9))) as response:
            data = response.read(2_000_000)
        root = ET.fromstring(data)
        nodes = [
            node for node in root.iter()
            if _market_tag_name(getattr(node, "tag", "")) in {"item", "entry"}
        ][:25]
        stories: List[Dict[str, Any]] = []
        for node in nodes:
            title = _market_child_text(node, {"title"})
            url = _market_item_link(node)
            if not title or not re.match(r"^https?://", url or "", re.I):
                continue
            published_text = _market_child_text(
                node,
                {"pubdate", "published", "updated", "date", "created"},
            )
            published_ms = _market_parse_date_ms(published_text, now_ms)
            stories.append({
                "source": source["name"],
                "badge": source["badge"],
                "title": title[:300],
                "url": url,
                "published_at_ms": published_ms,
                "_source_weight": source.get("weight") or 0,
                "_always_relevant": bool(source.get("always_relevant")),
            })
        return str(source["name"]), stories, ""
    except Exception as exc:
        return str(source["name"]), [], str(exc)


def _market_load_cache() -> Dict[str, Any]:
    try:
        if MARKET_NEWS_CACHE.exists():
            raw = json.loads(MARKET_NEWS_CACHE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    return {}


def _market_save_cache(payload: Dict[str, Any]) -> None:
    try:
        MARKET_NEWS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MARKET_NEWS_CACHE.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"Warning: could not save market narrative cache: {exc}")


def market_narrative_from_cache(now_ms: int) -> Dict[str, Any]:
    cached = _market_load_cache()
    stories = cached.get("stories") if isinstance(cached.get("stories"), list) else []
    return {
        "status": "cached" if stories else "warming",
        "updated_at_ms": safe_int(cached.get("updated_at_ms")) or now_ms,
        "refresh_seconds": 300,
        "source_count": safe_int(cached.get("source_count")),
        "sources_attempted": safe_int(cached.get("sources_attempted")) or len(MARKET_NEWS_SOURCES),
        "stories": stories[:5],
        "note": "Automated headline classification; informational only. Headlines link to the original publishers.",
    }


def build_market_narrative(now_ms: int, timeout: int, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    cached = _market_load_cache()
    cached_at = safe_int(cached.get("updated_at_ms"))
    cached_stories = cached.get("stories") if isinstance(cached.get("stories"), list) else []
    if cached_stories and cached_at and (now_ms - cached_at) < MARKET_NEWS_REFRESH_MS:
        return market_narrative_from_cache(now_ms)

    asset_terms = set()
    for row in (signals or [])[:40]:
        coin = _market_text(row.get("coin")).upper()
        if coin:
            asset_terms.add(coin)
            full_name = TOKEN_NAMES.get(coin)
            if full_name:
                asset_terms.add(full_name)

    all_rows: List[Dict[str, Any]] = []
    successful_sources = set()
    failures: List[str] = []
    worker_count = min(8, len(MARKET_NEWS_SOURCES))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_market_fetch_source, source, timeout, now_ms)
            for source in MARKET_NEWS_SOURCES
        ]
        for future in concurrent.futures.as_completed(futures):
            source_name, rows, error = future.result()
            if rows:
                successful_sources.add(source_name)
                all_rows.extend(rows)
            elif error:
                failures.append(f"{source_name}: {error}")

    ranked: List[Dict[str, Any]] = []
    for row in all_rows:
        published_ms = safe_int(row.get("published_at_ms")) or now_ms
        if published_ms > now_ms + 10 * 60 * 1000:
            published_ms = now_ms
        if now_ms - published_ms > MARKET_NEWS_MAX_AGE_MS:
            continue
        source = {
            "weight": row.pop("_source_weight", 0),
            "always_relevant": row.pop("_always_relevant", False),
        }
        relevance = _market_relevance(
            str(row.get("title") or ""),
            source,
            asset_terms,
            now_ms,
            published_ms,
        )
        if not source.get("always_relevant") and relevance < 18:
            continue
        sentiment, sentiment_score = _market_sentiment(str(row.get("title") or ""))
        row["published_at_ms"] = published_ms
        row["sentiment"] = sentiment
        row["sentiment_score"] = sentiment_score
        row["relevance_score"] = round(relevance, 2)
        ranked.append(row)

    ranked.sort(
        key=lambda row: (
            safe_float(row.get("relevance_score")),
            safe_int(row.get("published_at_ms")),
        ),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}
    for row in ranked:
        source_name = str(row.get("source") or "")
        if source_counts.get(source_name, 0) >= 2:
            continue
        if _market_title_is_duplicate(str(row.get("title") or ""), selected):
            continue
        selected.append(row)
        source_counts[source_name] = source_counts.get(source_name, 0) + 1
        if len(selected) >= 5:
            break

    if not selected and cached_stories:
        log("Market narrative refresh returned no usable stories; keeping last-good cache")
        return market_narrative_from_cache(now_ms)

    payload = {
        "status": "ok" if selected else "warming",
        "updated_at_ms": now_ms,
        "refresh_seconds": 300,
        "source_count": len(successful_sources),
        "sources_attempted": len(MARKET_NEWS_SOURCES),
        "stories": selected,
        "note": "Automated headline classification; informational only. Headlines link to the original publishers.",
    }
    _market_save_cache(payload)
    if failures:
        log(f"Market narrative: {len(successful_sources)}/{len(MARKET_NEWS_SOURCES)} sources active; {len(failures)} unavailable")
    else:
        log(f"Market narrative: all {len(MARKET_NEWS_SOURCES)} sources active")
    return payload
# COPYCAT_MARKET_NARRATIVE_V1_END

# COPYCAT_CATALYST_WATCH_V1_START
CATALYST_WATCH_REFRESH_MS = 30 * 60 * 1000
CATALYST_WATCH_MAX_AHEAD_MS = 90 * 24 * 60 * 60 * 1000
CATALYST_WATCH_CACHE = SCRIPT_DIR / "scanner_state" / "catalyst_watch_cache.json"
CATALYST_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CATALYST_BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
CATALYST_SNAPSHOT_URL = "https://hub.snapshot.org/graphql"

# Curated first-party governance spaces. Unknown/unverified community spaces are
# deliberately excluded so the public card does not surface spam proposals.
CATALYST_SNAPSHOT_SPACES = {
    "aave.eth": ("AAVE", "Aave"),
    "uniswapgovernance.eth": ("UNI", "Uniswap"),
    "arbitrumfoundation.eth": ("ARB", "Arbitrum"),
    "opcollective.eth": ("OP", "Optimism"),
    "ens.eth": ("ENS", "ENS"),
    "lido-snapshot.eth": ("LDO", "Lido"),
    "balancer.eth": ("BAL", "Balancer"),
    "safe.eth": ("SAFE", "Safe"),
    "stgdao.eth": ("STG", "Stargate"),
    "frax.eth": ("FXS", "Frax"),
    "curve.eth": ("CRV", "Curve"),
    "compound-governance.eth": ("COMP", "Compound"),
    "rocketpool-dao.eth": ("RPL", "Rocket Pool"),
    "sushi.eth": ("SUSHI", "Sushi"),
    "pancake.eth": ("CAKE", "PancakeSwap"),
    "apecoin.eth": ("APE", "ApeCoin"),
    "gitcoindao.eth": ("GTC", "Gitcoin"),
    "hop.eth": ("HOP", "Hop"),
}

CATALYST_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _catalyst_http_text(
    url: str,
    timeout: int,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    body = None
    headers = {
        "User-Agent": "CopycatCatalystWatch/1.0",
        "Accept": "text/html, text/calendar, application/json, */*;q=0.5",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(
        request,
        timeout=max(4, min(int(timeout or 8), 10)),
    ) as response:
        return response.read(2_000_000).decode("utf-8", errors="replace")


def _catalyst_date_ms(year: int, month: int, day: int) -> int:
    return int(
        datetime(
            int(year),
            int(month),
            int(day),
            12,
            0,
            0,
            tzinfo=timezone.utc,
        ).timestamp()
        * 1000
    )


def _catalyst_in_window(event_at_ms: int, now_ms: int) -> bool:
    # A small six-hour grace period keeps today's event visible throughout the day.
    return (
        event_at_ms >= now_ms - (6 * 60 * 60 * 1000)
        and event_at_ms <= now_ms + CATALYST_WATCH_MAX_AHEAD_MS
    )


def _catalyst_parse_bls_ics(text: str, now_ms: int) -> List[Dict[str, Any]]:
    unfolded: List[str] = []
    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw[1:]
        else:
            unfolded.append(raw.strip())

    events: List[Dict[str, Any]] = []
    current: Dict[str, str] = {}
    inside = False
    for line in unfolded:
        if line == "BEGIN:VEVENT":
            current = {}
            inside = True
            continue
        if line == "END:VEVENT":
            if inside:
                summary = _market_text(current.get("SUMMARY", ""))
                dt_value = current.get("DTSTART", "")
                date_match = re.search(r"(\d{4})(\d{2})(\d{2})", dt_value)
                if summary and date_match:
                    event_at_ms = _catalyst_date_ms(
                        safe_int(date_match.group(1)),
                        safe_int(date_match.group(2)),
                        safe_int(date_match.group(3)),
                    )
                    lower = summary.lower()
                    mapped = None
                    if "consumer price index" in lower:
                        mapped = ("CPI", "US CPI release", "HIGH")
                    elif "employment situation" in lower:
                        mapped = ("JOBS", "US jobs report", "HIGH")
                    elif "producer price index" in lower:
                        mapped = ("PPI", "US PPI release", "MEDIUM")
                    if mapped and _catalyst_in_window(event_at_ms, now_ms):
                        badge, title, impact = mapped
                        events.append({
                            "source": "U.S. Bureau of Labor Statistics",
                            "badge": badge,
                            "asset": "MACRO",
                            "title": title,
                            "url": current.get(
                                "URL",
                                "https://www.bls.gov/schedule/",
                            ),
                            "event_at_ms": event_at_ms,
                            "impact": impact,
                            "category": "macro",
                            "relevance_score": 12 if impact == "HIGH" else 8,
                        })
            current = {}
            inside = False
            continue
        if not inside or ":" not in line:
            continue
        key_part, value = line.split(":", 1)
        key = key_part.split(";", 1)[0].upper()
        if key in {"SUMMARY", "DTSTART", "URL"}:
            current[key] = value.replace("\\,", ",").replace("\\n", " ").strip()

    return events


def _catalyst_parse_fomc(text: str, now_ms: int) -> List[Dict[str, Any]]:
    clean = _market_text(text)
    headings = list(re.finditer(r"\b(20\d{2}) FOMC Meetings\b", clean))
    events: List[Dict[str, Any]] = []
    month_pattern = "|".join(
        name.title() for name in CATALYST_MONTHS.keys()
    )

    for index, heading in enumerate(headings):
        year = safe_int(heading.group(1))
        if year < datetime.now(timezone.utc).year:
            continue
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(clean)
        section = clean[heading.end():section_end]

        for match in re.finditer(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:\s*-\s*(\d{{1,2}}))?\*?\b",
            section,
            flags=re.I,
        ):
            prefix = section[max(0, match.start() - 18):match.start()].lower()
            if "released" in prefix:
                continue
            month = CATALYST_MONTHS.get(match.group(1).lower())
            decision_day = safe_int(match.group(3) or match.group(2))
            if not month or not decision_day:
                continue
            try:
                event_at_ms = _catalyst_date_ms(year, month, decision_day)
            except Exception:
                continue
            if not _catalyst_in_window(event_at_ms, now_ms):
                continue
            events.append({
                "source": "Federal Reserve",
                "badge": "FED",
                "asset": "MACRO",
                "title": "FOMC rate decision",
                "url": CATALYST_FOMC_URL,
                "event_at_ms": event_at_ms,
                "impact": "HIGH",
                "category": "macro",
                "relevance_score": 14,
            })

    return events


def _catalyst_fetch_snapshot(now_ms: int, timeout: int) -> List[Dict[str, Any]]:
    space_ids = json.dumps(list(CATALYST_SNAPSHOT_SPACES.keys()))
    query = f"""
    query {{
      proposals(
        first: 80,
        skip: 0,
        where: {{
          space_in: {space_ids},
          state: "active"
        }},
        orderBy: "end",
        orderDirection: asc
      ) {{
        id
        title
        end
        state
        space {{
          id
          name
        }}
      }}
    }}
    """
    raw = _catalyst_http_text(
        CATALYST_SNAPSHOT_URL,
        timeout,
        method="POST",
        payload={"query": query},
    )
    decoded = json.loads(raw)
    rows = (
        decoded.get("data", {}).get("proposals", [])
        if isinstance(decoded, dict)
        else []
    )
    events: List[Dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        space = row.get("space") if isinstance(row.get("space"), dict) else {}
        space_id = str(space.get("id") or "").lower()
        mapped = CATALYST_SNAPSHOT_SPACES.get(space_id)
        if not mapped:
            continue
        asset, label = mapped
        event_at_ms = safe_int(row.get("end")) * 1000
        if not _catalyst_in_window(event_at_ms, now_ms):
            continue
        proposal_id = str(row.get("id") or "")
        title = _market_text(row.get("title"))[:180]
        if not proposal_id or not title:
            continue
        events.append({
            "source": f"{label} governance",
            "badge": asset[:5],
            "asset": asset,
            "title": title,
            "url": f"https://snapshot.org/#/{space_id}/proposal/{proposal_id}",
            "event_at_ms": event_at_ms,
            "impact": "MEDIUM",
            "category": "governance",
            "relevance_score": 10,
        })
    return events


def _catalyst_load_cache() -> Dict[str, Any]:
    try:
        if CATALYST_WATCH_CACHE.exists():
            raw = json.loads(CATALYST_WATCH_CACHE.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    return {}


def _catalyst_save_cache(payload: Dict[str, Any]) -> None:
    try:
        CATALYST_WATCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CATALYST_WATCH_CACHE.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"Warning: could not save catalyst cache: {exc}")


def catalyst_watch_from_cache(now_ms: int) -> Dict[str, Any]:
    cached = _catalyst_load_cache()
    events = cached.get("events") if isinstance(cached.get("events"), list) else []
    current_events = [
        row for row in events
        if isinstance(row, dict)
        and _catalyst_in_window(safe_int(row.get("event_at_ms")), now_ms)
    ]
    return {
        "status": "cached" if current_events else "warming",
        "updated_at_ms": safe_int(cached.get("updated_at_ms")) or now_ms,
        "refresh_seconds": 1800,
        "source_count": safe_int(cached.get("source_count")),
        "events": current_events[:3],
        "note": "Official-source dates; schedules and governance deadlines can change.",
    }


def _catalyst_select_events(
    candidates: List[Dict[str, Any]],
    signals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    signal_assets = {
        _market_text(row.get("coin")).upper()
        for row in (signals or [])[:80]
        if isinstance(row, dict) and _market_text(row.get("coin"))
    }
    unique: List[Dict[str, Any]] = []
    seen = set()
    for row in candidates:
        key = (
            str(row.get("source") or ""),
            str(row.get("title") or "").lower(),
            safe_int(row.get("event_at_ms")),
        )
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        if str(item.get("asset") or "").upper() in signal_assets:
            item["relevance_score"] = safe_float(item.get("relevance_score")) + 12
        unique.append(item)

    governance = sorted(
        [row for row in unique if row.get("category") == "governance"],
        key=lambda row: (
            -safe_float(row.get("relevance_score")),
            safe_int(row.get("event_at_ms")),
        ),
    )
    macro = sorted(
        [row for row in unique if row.get("category") == "macro"],
        key=lambda row: safe_int(row.get("event_at_ms")),
    )

    selected: List[Dict[str, Any]] = []
    if governance:
        selected.append(governance[0])
    for row in macro:
        if len(selected) >= 3:
            break
        selected.append(row)
    for row in governance[1:]:
        if len(selected) >= 3:
            break
        selected.append(row)

    selected.sort(key=lambda row: safe_int(row.get("event_at_ms")))
    return selected[:3]


def build_catalyst_watch(
    now_ms: int,
    timeout: int,
    signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    cached = _catalyst_load_cache()
    cached_at = safe_int(cached.get("updated_at_ms"))
    cached_events = cached.get("events") if isinstance(cached.get("events"), list) else []
    if cached_events and cached_at and now_ms - cached_at < CATALYST_WATCH_REFRESH_MS:
        return catalyst_watch_from_cache(now_ms)

    candidates: List[Dict[str, Any]] = []
    active_sources = set()
    failures: List[str] = []

    def fetch_bls() -> Tuple[str, List[Dict[str, Any]]]:
        text = _catalyst_http_text(CATALYST_BLS_ICS_URL, timeout)
        return "BLS", _catalyst_parse_bls_ics(text, now_ms)

    def fetch_fomc() -> Tuple[str, List[Dict[str, Any]]]:
        text = _catalyst_http_text(CATALYST_FOMC_URL, timeout)
        return "Federal Reserve", _catalyst_parse_fomc(text, now_ms)

    def fetch_snapshot() -> Tuple[str, List[Dict[str, Any]]]:
        return "Snapshot", _catalyst_fetch_snapshot(now_ms, timeout)

    jobs = [fetch_bls, fetch_fomc, fetch_snapshot]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(job): job.__name__ for job in jobs}
        for future in concurrent.futures.as_completed(future_map):
            try:
                source_name, rows = future.result()
                if rows:
                    active_sources.add(source_name)
                    candidates.extend(rows)
            except Exception as exc:
                failures.append(f"{future_map[future]}: {exc}")

    selected = _catalyst_select_events(candidates, signals)
    if not selected and cached_events:
        log("Catalyst watch refresh returned no usable events; keeping last-good cache")
        return catalyst_watch_from_cache(now_ms)

    payload = {
        "status": "ok" if selected else "warming",
        "updated_at_ms": now_ms,
        "refresh_seconds": 1800,
        "source_count": len(active_sources),
        "events": selected,
        "note": "Official-source dates; schedules and governance deadlines can change.",
    }
    _catalyst_save_cache(payload)
    log(
        f"Catalyst watch: {len(selected)} event(s), "
        f"{len(active_sources)}/3 sources active"
        + (f"; {len(failures)} unavailable" if failures else "")
    )
    return payload


def _catalyst_watch_self_test() -> List[str]:
    failures: List[str] = []
    fixed_now = _catalyst_date_ms(2026, 1, 1)

    sample_ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260110T083000
SUMMARY:Consumer Price Index
URL:https://www.bls.gov/cpi/
END:VEVENT
BEGIN:VEVENT
DTSTART:20260115T083000
SUMMARY:Producer Price Index
END:VEVENT
END:VCALENDAR"""
    bls_rows = _catalyst_parse_bls_ics(sample_ics, fixed_now)
    if [row.get("badge") for row in bls_rows] != ["CPI", "PPI"]:
        failures.append("BLS iCalendar parser did not identify CPI and PPI")

    sample_fomc = (
        "2026 FOMC Meetings January 27-28 Statement: PDF "
        "Minutes: PDF (Released February 18, 2026) "
        "March 17-18* Statement: PDF 2025 FOMC Meetings"
    )
    fomc_rows = _catalyst_parse_fomc(sample_fomc, fixed_now)
    fomc_dates = [safe_int(row.get("event_at_ms")) for row in fomc_rows]
    if _catalyst_date_ms(2026, 1, 28) not in fomc_dates:
        failures.append("FOMC parser did not identify the decision day")
    if _catalyst_date_ms(2026, 2, 18) in fomc_dates:
        failures.append("FOMC parser incorrectly treated a minutes release as a meeting")

    sample_candidates = [
        {
            "source": "Federal Reserve",
            "title": "FOMC rate decision",
            "asset": "MACRO",
            "event_at_ms": _catalyst_date_ms(2026, 1, 28),
            "category": "macro",
            "relevance_score": 14,
        },
        {
            "source": "Aave governance",
            "title": "Risk parameter vote",
            "asset": "AAVE",
            "event_at_ms": _catalyst_date_ms(2026, 1, 20),
            "category": "governance",
            "relevance_score": 10,
        },
    ]
    selected = _catalyst_select_events(sample_candidates, [{"coin": "AAVE"}])
    if not selected or selected[0].get("asset") != "AAVE":
        failures.append("Tracked-asset governance relevance was not preserved")

    return failures
# COPYCAT_CATALYST_WATCH_V1_END



def build_snapshots(wallets: List[str], config: Config) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    now_ms = int(time.time() * 1000)
    scanner = read_scanner_results()
    scanner_scored = safe_int(scanner.get('candidate_wallets_scored'))
    scanner_discovered = safe_int(scanner.get('wallets_discovered_from_recent_trades'))
    scanner_selected = safe_int(scanner.get('selected_wallet_count'))
    registry_summary = read_registry_summary_counts()
    registry_wallets = safe_int(registry_summary.get('registry_wallets'))
    registry_scan_history = safe_int(registry_summary.get('registry_scan_history'))
    registry_discoveries = safe_int(registry_summary.get('registry_discoveries'))
    registry_indexed = registry_wallets or scanner_scored or len(wallets)
    registry_discovered_total = registry_discoveries or scanner_discovered
    # Copycat live dashboard registry display fields v1
    dashboard_display_scored = registry_indexed
    dashboard_display_discovered = registry_discovered_total
    mids = get_mids(config.request_timeout_seconds)
    meta = get_meta(config.request_timeout_seconds)
    states: List[Dict[str, Any]] = []
    orders: List[Dict[str, Any]] = []
    start_ms = now_ms - config.fill_lookback_minutes * 60 * 1000
    wallet_cache = load_wallet_state_cache()
    live_state_count = 0
    stale_state_count = 0
    missing_state_wallets: List[str] = []

    log(f"Fetching Hyperliquid state for {len(wallets)} wallet(s)")
    for idx, wallet in enumerate(wallets, 1):
        state = get_state(wallet, config.request_timeout_seconds)
        state_status = "live"
        if state:
            remember_wallet_state(wallet_cache, wallet, state, now_ms)
            live_state_count += 1
        else:
            cached = cached_state_for_wallet(wallet_cache, wallet, now_ms, config.state_cache_max_age_seconds)
            if cached:
                state = cached
                state_status = "stale"
                stale_state_count += 1
                log(f"Wallet {short_wallet(wallet)} using stale cached state ({state.get('_copycat_cache_age_seconds', 0)}s old)")
            else:
                state_status = "missing"
                missing_state_wallets.append(wallet)
        if state:
            state["_wallet"] = wallet
            state["_copycat_state_status"] = state_status
            states.append(state)
        time.sleep(max(0.05, config.request_pause_seconds / 2))
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
        time.sleep(config.request_pause_seconds)
        if idx % 10 == 0:
            log(f"Fetched {idx}/{len(wallets)} wallet(s)")
    save_wallet_state_cache(wallet_cache)

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
        state_status = str(state.get("_copycat_state_status") or "live")
        wallet_rows.append(
            {
                "wallet": wallet,
                "wallet_label": short_wallet(wallet),
                "account_value_usd": round(account_value, 2),
                "open_position_value_usd": round(wallet_open, 2),
                "open_positions": wallet_position_count,
                "data_status": state_status,
                "stale": state_status != "live",
                "cache_age_seconds": safe_int(state.get("_copycat_cache_age_seconds")),
                "source": "local_hyperliquid",
            }
        )

    wallet_rows_by_address = {str(row.get("wallet", "")).lower(): row for row in wallet_rows}
    for wallet in wallets:
        if wallet.lower() not in wallet_rows_by_address:
            wallet_rows.append(
                {
                    "wallet": wallet,
                    "wallet_label": short_wallet(wallet),
                    "account_value_usd": 0.0,
                    "open_position_value_usd": 0.0,
                    "open_positions": 0,
                    "data_status": "missing",
                    "stale": True,
                    "cache_age_seconds": None,
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

    missing_state_count = len(missing_state_wallets)
    usable_state_count = len(states)
    if live_state_count == len(wallets):
        data_status = "healthy"
        data_msg = "Local Hyperliquid snapshot publisher active with all 50 wallet states live"
    elif usable_state_count == len(wallets):
        data_status = "syncing"
        data_msg = f"Rate limited by Hyperliquid; using {live_state_count} live and {stale_state_count} cached wallet states"
    elif usable_state_count:
        data_status = "degraded"
        data_msg = f"Rate limited by Hyperliquid; {live_state_count} live, {stale_state_count} cached, {missing_state_count} missing wallet states"
    else:
        data_status = "degraded"
        data_msg = "No wallet states fetched; check wallets.txt and network"
    summary = {
        "latest_signal_ts_ms": now_ms,
        "latest_position_ts_ms": now_ms,
        "latest_live_state_ts_ms": now_ms,
        "live_state_active": live_state_count > 0,
        "live_coverage_mode": "local_snapshot",
        "live_wallets": live_state_count,
        "snapshot_wallets": usable_state_count,
        "configured_wallets": len(wallets),
        "wallets_with_live_state": live_state_count,
        "wallets_with_stale_state": stale_state_count,
        "wallets_missing_state": missing_state_count,
        "qualified_wallets": len(wallets),
        "tracked_active_wallets": len(wallets),
        "selected_wallet_count": scanner_selected or len(wallets),
        "scanner_candidate_wallets_scored": dashboard_display_scored,
        "wallets_discovered_from_recent_trades": dashboard_display_discovered,
        "latest_scanner_candidate_wallets_scored": scanner_scored,
        "latest_recent_trade_wallets_discovered": scanner_discovered,
        "registry_wallets": registry_wallets,
        "registry_scan_history": registry_scan_history,
        "registry_discoveries": registry_discoveries,
        "indexed_wallets": registry_indexed,
        "known_wallet_candidates": registry_indexed,
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
        "top_claim_ready": False,
        "top_claim_min_indexed_wallets": 10000,
        "claim_label": f"Top {len(wallets)} Copycat-ranked wallets from {registry_indexed:,} locally indexed Hyperliquid candidates",
    }

    insights: List[Dict[str, Any]] = []
    if signals:
        top_signal = signals[0]
        pct = round(abs(safe_float(top_signal.get("signal"))) * 100)
        side = "Long" if safe_float(top_signal.get("signal")) >= 0 else "Short"
        insights.append({"type": "top_signal", "label": "Top conviction asset", "coin": top_signal["coin"], "detail": f"{pct}% {side} Â· {top_signal.get('confidence')}", "row": top_signal})
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
        "wallets_live": live_state_count,
        "wallets_stale": stale_state_count,
        "wallets_missing": missing_state_count,
        "scanner_candidate_wallets_scored": dashboard_display_scored,
        "wallets_discovered_from_recent_trades": dashboard_display_discovered,
        "latest_scanner_candidate_wallets_scored": scanner_scored,
        "latest_recent_trade_wallets_discovered": scanner_discovered,
        "registry_wallets": registry_wallets,
        "registry_scan_history": registry_scan_history,
        "registry_discoveries": registry_discoveries,
        "selected_wallet_count": scanner_selected or len(wallet_rows),
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
    leaderboard["data"] = leaderboard.get("rows", [])
    token_screener["data"] = token_screener.get("rows", [])

    coverage = {
        "status": "ok" if states else "degraded",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "wallets_configured": len(wallets),
        "wallets_fetched": live_state_count,
        "wallets_usable": usable_state_count,
        "wallets_stale": stale_state_count,
        "wallets_missing": missing_state_count,
        "assets_with_signals": len(signals),
        "recent_orders": len(orders),
        "storage_mode": "r2_snapshot_overwrite",
        "supabase_required": False,
        "historical_backfill_enabled": False,
        "message": data_msg,
        "scanner_candidate_wallets_scored": dashboard_display_scored,
        "wallets_discovered_from_recent_trades": dashboard_display_discovered,
        "latest_scanner_candidate_wallets_scored": scanner_scored,
        "latest_recent_trade_wallets_discovered": scanner_discovered,
        "registry_wallets": registry_wallets,
        "registry_scan_history": registry_scan_history,
        "registry_discoveries": registry_discoveries,
        "selected_wallet_count": scanner_selected or len(wallets),
        "top_claim_ready": False,
        "claim_label": f"Top {len(wallets)} Copycat-ranked wallets from {registry_indexed:,} locally indexed Hyperliquid candidates",
    }
    platform_health = {
        "status": "ok" if states else "degraded",
        "service": "copycat-snapshot-publisher",
        "updated_at_ms": now_ms,
        "frontend": "cloudflare_pages",
        "data_delivery": "cloudflare_r2_snapshots",
        "database_required_for_dashboard": False,
        "wallets": len(wallets),
        "wallets_live": live_state_count,
        "wallets_stale": stale_state_count,
        "wallets_missing": missing_state_count,
        "scanner_candidate_wallets_scored": dashboard_display_scored,
        "wallets_discovered_from_recent_trades": dashboard_display_discovered,
        "latest_scanner_candidate_wallets_scored": scanner_scored,
        "latest_recent_trade_wallets_discovered": scanner_discovered,
        "selected_wallet_count": scanner_selected or len(wallets),
        "render_required": False,
        "supabase_required": False,
    }
    status = {
        "status": "ok" if states else "degraded",
        "product": "Copycat Data API",
        "version": "snapshot-v1",
        "source": "local_hyperliquid_snapshot",
        "updated_at_ms": now_ms,
        "tracked_active_wallets": len(wallets),
        "wallets_live": live_state_count,
        "wallets_stale": stale_state_count,
        "wallets_missing": missing_state_count,
        "selected_wallet_count": scanner_selected or len(wallets),
        "scanner_candidate_wallets_scored": scanner_scored,
        "wallets_discovered_from_recent_trades": scanner_discovered,
        "assets_with_signals": len(signals),
        "recent_orders": len(orders),
        "snapshot_mode": True,
        "top_claim_ready": False,
    }
    performance_index = build_performance_index_snapshot(now_ms, mids, signals, targets, config)

    scanner_rows = scanner.get('top_rows') if isinstance(scanner.get('top_rows'), list) else []
    ranking_wallets = []
    source_rows = scanner_rows or sorted(wallet_rows, key=lambda r: (r.get('account_value_usd', 0), r.get('open_position_value_usd', 0)), reverse=True)
    for i, row in enumerate(source_rows[:50], 1):
        item = dict(row)
        item['rank'] = item.get('rank') or i
        item['wallet_label'] = item.get('short_wallet') or item.get('wallet_label') or short_wallet(str(item.get('wallet', '')))
        item['copycat_score'] = item.get('copycat_score') or item.get('score') or 0
        item['ranking_formula'] = item.get('ranking_formula') or 'local_scanner_v1_live_state'
        ranking_wallets.append(item)
    ranking_audit = {
        'status': 'ok' if ranking_wallets else 'degraded',
        'source': 'local_scanner_v1_snapshot',
        'updated_at_ms': now_ms,
        'wallets_scanned': registry_indexed,
        'wallets_discovered_from_recent_trades': scanner_discovered,
        'registry_wallets': registry_wallets,
        'registry_scan_history': registry_scan_history,
        'registry_discoveries': registry_discoveries,
        'selected_wallet_count': scanner_selected or len(ranking_wallets),
        'method_note': scanner.get('method_note') or 'Local scanner v1 ranking from visible Hyperliquid live state, not a full historical profit audit.',
        'wallets': ranking_wallets,
    }
    audit_snapshot = {
        'overall_status': 'free_mode_ok' if states else 'degraded',
        'latest_signal_ts_ms': now_ms,
        'checks': [
            {'name': 'R2 snapshot publisher', 'status': 'pass' if states else 'fail', 'severity': 'critical', 'detail': data_msg},
            {'name': 'Configured wallet coverage', 'status': 'pass' if len(wallet_rows) == len(wallets) else 'warn', 'severity': 'critical', 'detail': f'{len(wallet_rows)}/{len(wallets)} ranked wallet slots included; live={live_state_count}, stale={stale_state_count}, missing={missing_state_count}'},
            {'name': 'Supabase dependency', 'status': 'pass', 'severity': 'info', 'detail': 'Public dashboard does not require Supabase in free mode.'},
            {'name': 'Render dependency', 'status': 'pass', 'severity': 'info', 'detail': 'Public read-only pages are served by Cloudflare/R2 snapshots.'},
            {'name': 'Ranking claim guard', 'status': 'pass', 'severity': 'info', 'detail': 'Broad all-Hyperliquid top-50 claim is disabled until a larger audited universe exists.'},
        ],
        'totals': {
            'snapshot_rollup': {'tracked_total': round(tracked_account_value, 2)},
            'position_rollup': {'open_total': round(open_value_total, 2), 'positions': open_positions},
            'scanner_rollup': {'candidate_wallets_scored': scanner_scored, 'selected_wallet_count': scanner_selected or len(wallets)},
        },
        'free_mode': True,
    }
    free_mode_status = {
        'status': 'ok' if states else 'degraded',
        'updated_at_ms': now_ms,
        'site_mode': 'cloudflare_pages_r2_snapshot',
        'render_required': False,
        'supabase_required': False,
        'public_readonly': True,
        'tracked_wallets': len(wallets),
        'wallets_live': live_state_count,
        'wallets_stale': stale_state_count,
        'wallets_missing': missing_state_count,
        'scanner_candidate_wallets_scored': dashboard_display_scored,
        'wallets_discovered_from_recent_trades': dashboard_display_discovered,
        'latest_scanner_candidate_wallets_scored': scanner_scored,
        'latest_recent_trade_wallets_discovered': scanner_discovered,
        'registry_wallets': registry_wallets,
        'registry_scan_history': registry_scan_history,
        'registry_discoveries': registry_discoveries,
        'disabled_until_paid_backend': ['login_auth', 'private_api_keys', 'dynamic_database_queries', 'full_historical_backtests'],
    }
    scanner_status = {
        'status': scanner.get('status') or ('ok' if scanner_scored else 'warming'),
        'updated_at_ms': scanner.get('updated_at_ms') or now_ms,
        'candidate_wallets_scored': dashboard_display_scored,
        'wallets_discovered_from_recent_trades': dashboard_display_discovered,
        'latest_scanner_candidate_wallets_scored': scanner_scored,
        'latest_recent_trade_wallets_discovered': scanner_discovered,
        'registry_wallets': registry_wallets,
        'registry_scan_history': registry_scan_history,
        'registry_discoveries': registry_discoveries,
        'wallets_scanned': registry_indexed,
        'selected_wallet_count': scanner_selected or len(wallets),
        'coins_scanned': scanner.get('coins_scanned') or [],
        'method_note': scanner.get('method_note') or 'Scanner results appear after run_local_scanner_update_wallets.cmd.',
    }
    # Copycat force registry summary finalizer v1
    # Make the already-live dashboard fields show the larger long-running registry counts.
    try:
        if isinstance(feed, dict) and isinstance(feed.get("summary"), dict):
            _registry_summary = read_registry_summary_counts()
            _registry_wallets = safe_int(_registry_summary.get("registry_wallets"))
            _registry_scan_history = safe_int(_registry_summary.get("registry_scan_history"))
            _registry_discoveries = safe_int(_registry_summary.get("registry_discoveries"))
            _registry_indexed = _registry_wallets or safe_int(scanner_scored) or len(wallets)
            _registry_discovered_total = _registry_discoveries or safe_int(scanner_discovered)
            feed["summary"]["scanner_candidate_wallets_scored"] = _registry_indexed
            feed["summary"]["wallets_discovered_from_recent_trades"] = _registry_discovered_total
            feed["summary"]["latest_scanner_candidate_wallets_scored"] = safe_int(scanner_scored)
            feed["summary"]["latest_recent_trade_wallets_discovered"] = safe_int(scanner_discovered)
            feed["summary"]["registry_wallets"] = _registry_wallets
            feed["summary"]["registry_scan_history"] = _registry_scan_history
            feed["summary"]["registry_discoveries"] = _registry_discoveries
            feed["summary"]["indexed_wallets"] = _registry_indexed
            feed["summary"]["known_wallet_candidates"] = _registry_indexed
            feed["summary"]["claim_label"] = f"Top {len(wallets)} Copycat-ranked wallets from {_registry_indexed:,} locally indexed Hyperliquid candidates"
        for _obj in [tick, leaderboard, platform_health, scanner_status]:
            if isinstance(_obj, dict):
                _obj["scanner_candidate_wallets_scored"] = _registry_indexed
                _obj["wallets_discovered_from_recent_trades"] = _registry_discovered_total
                _obj["registry_wallets"] = _registry_wallets
                _obj["registry_scan_history"] = _registry_scan_history
                _obj["registry_discoveries"] = _registry_discoveries
                _obj["latest_scanner_candidate_wallets_scored"] = safe_int(scanner_scored)
                _obj["latest_recent_trade_wallets_discovered"] = safe_int(scanner_discovered)
    except Exception as _registry_summary_error:
        log(f"Registry summary finalizer skipped: {_registry_summary_error}")


    try:
        market_narrative = build_market_narrative(
            now_ms,
            config.request_timeout_seconds,
            signals,
        )
    except Exception as exc:
        log(f"Market narrative warning: {exc}")
        market_narrative = market_narrative_from_cache(now_ms)
    feed["market_narrative"] = market_narrative
    try:
        catalyst_watch = build_catalyst_watch(
            now_ms,
            config.request_timeout_seconds,
            signals,
        )
    except Exception as exc:
        log(f"Catalyst watch warning: {exc}")
        catalyst_watch = catalyst_watch_from_cache(now_ms)
    feed["catalyst_watch"] = catalyst_watch

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
        "api/ranking-audit.json": ("application/json", ranking_audit),
        "api/audit.json": ("application/json", audit_snapshot),
        "api/free-mode-status.json": ("application/json", free_mode_status),
        "api/scanner-status.json": ("application/json", scanner_status),
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
    log(f"Interval: {config.interval_seconds}s | max wallets: {config.max_wallets} | request pause: {config.request_pause_seconds:.2f}s | local only: {config.local_only}")
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


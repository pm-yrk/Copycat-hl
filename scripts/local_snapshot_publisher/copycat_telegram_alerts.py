from __future__ import annotations
import argparse, datetime as dt, json, os, time, urllib.parse, urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / "publisher.env"
STATE_PATH = ROOT / "telegram_alert_state.json"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "telegram_alerts.log"
DEFAULT_FEED = Path(r"C:\copycat_snapshot_out\dashboard-feed.json")

def log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_env() -> dict[str, str]:
    values = {}
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k.startswith("COPYCAT_"):
            values[k] = v
    return values

def load_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        log(f"Could not read {path}: {exc}")
    return fallback

def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")

def money(value: Any) -> str:
    try:
        return "$" + f"{float(value or 0):,.0f}"
    except Exception:
        return "$0"

def short_wallet(w: Any) -> str:
    s = str(w or "")
    return (s[:6] + "…" + s[-4:]) if len(s) >= 10 else (s or "unknown wallet")

def order_key(o: dict[str, Any]) -> str:
    try:
        value = round(float(o.get("delta_value_usd") or o.get("notional_usd") or 0))
    except Exception:
        value = 0
    return ":".join([str(o.get("source") or "snapshot"), str(o.get("wallet") or ""), str(o.get("coin") or ""), str(o.get("ts_ms") or ""), str(o.get("side") or ""), str(value)])

def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        parsed = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if not parsed.get("ok"):
        raise RuntimeError(str(parsed))

def build_test_message(feed: dict[str, Any]) -> str:
    summary = feed.get("summary") or {}
    orders = feed.get("orders") or []
    scanned = int(summary.get("scanner_candidate_wallets_scored") or summary.get("indexed_wallets") or 0)
    discoveries = int(summary.get("wallets_discovered_from_recent_trades") or summary.get("registry_discoveries") or 0)
    live = int(summary.get("live_wallets") or 0)
    qualified = int(summary.get("qualified_wallets") or 0)
    lines = [
        "Copycat Telegram alerts connected ✅",
        f"Scanned candidates: {scanned:,}",
        f"Recent-trade discoveries: {discoveries:,}",
        f"Live wallets: {live}/{qualified}",
    ]
    if orders:
        o = orders[0]
        lines.append(f"Latest order: {o.get('side','?')} {o.get('coin','?')} {money(o.get('delta_value_usd') or o.get('notional_usd'))} by {o.get('wallet_label') or short_wallet(o.get('wallet'))}")
    claim = summary.get("claim_label")
    if claim:
        lines.append(str(claim))
    return "\n".join(lines)

def collect_alerts(feed_path: Path, feed: dict[str, Any], state: dict[str, Any], env: dict[str, str]) -> list[str]:
    now = time.time()
    summary = feed.get("summary") or {}
    orders = feed.get("orders") or []
    alerts = []

    if not state.get("started_sent"):
        alerts.append("Copycat Telegram alerts are now watching ✅")
        state["started_sent"] = True

    stale_minutes = int(env.get("COPYCAT_TELEGRAM_STALE_MINUTES", "10") or 10)
    try:
        age_seconds = now - feed_path.stat().st_mtime
        was_stale = bool(state.get("feed_was_stale"))
        if age_seconds > stale_minutes * 60 and not was_stale:
            alerts.append(f"⚠️ Copycat feed looks stale: dashboard-feed.json is {int(age_seconds // 60)} minutes old.")
            state["feed_was_stale"] = True
        elif age_seconds <= stale_minutes * 60:
            if was_stale:
                alerts.append("✅ Copycat feed freshness recovered.")
            state["feed_was_stale"] = False
    except Exception as exc:
        alerts.append(f"⚠️ Could not check Copycat feed freshness: {exc}")

    quality = str(summary.get("data_quality_status") or "unknown").lower()
    last_quality = str(state.get("last_data_quality_status") or "")
    if quality and quality != last_quality:
        if quality != "healthy":
            msg = summary.get("data_quality_message") or "Dashboard data quality is not healthy."
            alerts.append(f"⚠️ Copycat data quality: {quality}\n{msg}")
        elif last_quality and last_quality != "healthy":
            alerts.append("✅ Copycat data quality recovered: healthy")
        state["last_data_quality_status"] = quality

    discoveries = int(summary.get("wallets_discovered_from_recent_trades") or summary.get("registry_discoveries") or 0)
    base = int(env.get("COPYCAT_TELEGRAM_DISCOVERY_MILESTONE_BASE", "100000") or 100000)
    step = int(env.get("COPYCAT_TELEGRAM_DISCOVERY_MILESTONE_STEP", "5000") or 5000)
    if discoveries >= base and step > 0:
        milestone = (discoveries // step) * step
        last = int(state.get("last_discovery_milestone") or 0)
        if milestone > last:
            scanned = int(summary.get("scanner_candidate_wallets_scored") or summary.get("indexed_wallets") or 0)
            alerts.append(f"🚀 Copycat discovery milestone: {milestone:,} recent-trade discoveries\nIndexed candidates: {scanned:,}")
            state["last_discovery_milestone"] = milestone

    candidates = int(summary.get("registry_wallets") or summary.get("known_wallet_candidates") or summary.get("indexed_wallets") or 0)
    candidate_step = int(env.get("COPYCAT_TELEGRAM_CANDIDATE_MILESTONE_STEP", "100") or 100)
    if candidates > 0 and candidate_step > 0:
        milestone = (candidates // candidate_step) * candidate_step
        last = int(state.get("last_candidate_milestone") or 0)
        if milestone >= 600 and milestone > last:
            alerts.append(f"📈 Copycat candidate universe milestone: {milestone:,} indexed wallet candidates")
            state["last_candidate_milestone"] = milestone

    threshold = float(env.get("COPYCAT_TELEGRAM_LARGE_ORDER_USD", "100000") or 100000)
    seen = list(state.get("seen_large_order_keys") or [])
    seen_set = set(seen)
    for o in orders[:12]:
        try:
            value = abs(float(o.get("delta_value_usd") or o.get("notional_usd") or 0))
        except Exception:
            value = 0
        key = order_key(o)
        if value >= threshold and key not in seen_set:
            wallet = o.get("wallet")
            url = f"https://hypurrscan.io/address/{wallet}" if isinstance(wallet, str) and wallet.startswith("0x") else ""
            text = f"🐋 Large Copycat order\n{o.get('side','?')} {o.get('coin','?')} · {money(value)}\nWallet: {o.get('wallet_label') or short_wallet(wallet)}"
            if url:
                text += f"\n{url}"
            alerts.append(text)
            seen.append(key)
            seen_set.add(key)
            break
    state["seen_large_order_keys"] = seen[-250:]
    return alerts

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    env = load_env()
    token = env.get("COPYCAT_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("COPYCAT_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log("Telegram token/chat id missing. Add COPYCAT_TELEGRAM_BOT_TOKEN and COPYCAT_TELEGRAM_CHAT_ID to publisher.env.")
        return 1

    feed_path = Path(env.get("COPYCAT_DASHBOARD_FEED_PATH", str(DEFAULT_FEED)))
    feed = load_json(feed_path, {})
    if not isinstance(feed, dict) or not feed:
        log(f"Could not load dashboard feed: {feed_path}")
        return 1

    state = load_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}

    try:
        if args.test:
            send_telegram(token, chat_id, build_test_message(feed))
            log("Sent Telegram test/status alert.")
            return 0

        alerts = collect_alerts(feed_path, feed, state, env)
        save_json(STATE_PATH, state)
        if not alerts:
            log("No Telegram alert conditions met.")
            return 0
        for text in alerts:
            send_telegram(token, chat_id, text)
            log("Sent Telegram alert: " + text.splitlines()[0])
        return 0
    except Exception as exc:
        log(f"Telegram alert failed: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

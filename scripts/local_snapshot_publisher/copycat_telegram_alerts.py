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

def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def signed_money(value: Any) -> str:
    amount = as_float(value)
    sign = "+" if amount > 0 else ("-" if amount < 0 else "")
    return sign + "$" + f"{abs(amount):,.0f}"

def utc_label(timestamp_ms: Any = None) -> str:
    timestamp = as_float(timestamp_ms, time.time() * 1000) / 1000
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).strftime("%d %b %Y %H:%M UTC")

def age_label(age_seconds: float) -> str:
    if age_seconds < 90:
        return "under 2 minutes old"
    minutes = int(age_seconds // 60)
    return f"{minutes} minutes old" if minutes < 90 else f"{minutes // 60}h {minutes % 60:02d}m old"

def signal_value(row: dict[str, Any]) -> float:
    existing = maybe_float(row.get("signal"))
    if existing is not None:
        return existing
    long_value = max(0.0, as_float(row.get("value_long_usd")))
    short_value = max(0.0, as_float(row.get("value_short_usd")))
    total = long_value + short_value
    if total <= 0:
        return 0.0
    return long_value / total if long_value >= short_value else -short_value / total

def signal_direction(value: float) -> str:
    if value > 0.05:
        return "LONG"
    if value < -0.05:
        return "SHORT"
    return "NEUTRAL"

def signal_confidence(row: dict[str, Any]) -> str:
    text = str(row.get("confidence") or "").strip()
    return text.title() if text else "Unrated"

def signed_target(row: dict[str, Any]) -> float:
    raw = maybe_float(row.get("target_weight"))
    if raw is None:
        raw = maybe_float(row.get("index_weight"))
    if raw is None:
        return 0.0
    direction = str(row.get("direction") or row.get("signal_direction") or "").lower()
    if raw > 0 and "short" in direction:
        return -abs(raw)
    return raw

def story_key(story: dict[str, Any]) -> str:
    url = str(story.get("url") or story.get("link") or story.get("source_url") or "").strip()
    if url:
        return url
    return "|".join([str(story.get("source") or ""), str(story.get("title") or ""), str(story.get("published_at_ms") or "")])

def catalyst_key(event: dict[str, Any]) -> str:
    return "|".join([str(event.get("source") or ""), str(event.get("title") or ""), str(event.get("event_at_ms") or "")])

def build_test_message(feed: dict[str, Any]) -> str:
    summary = feed.get("summary") or {}
    signals = feed.get("signals") or []
    top = signals[0] if signals else {}
    lines = [
        "Copycat Telegram intelligence is connected ✅",
        "Schedule: one hourly brief + meaningful trigger/news alerts",
        f"Live cohort: {as_int(summary.get('live_wallets')):,}/{as_int(summary.get('qualified_wallets')):,} qualified",
        f"Data quality: {str(summary.get('data_quality_status') or 'unknown').lower()}",
        "Candidate-count milestone spam: disabled",
    ]
    if isinstance(top, dict) and top:
        value = signal_value(top)
        lines.append(f"Lead signal: {top.get('coin', '?')} {signal_direction(value)} {abs(value) * 100:.0f}% · {signal_confidence(top)}")
    return "\n".join(lines)

def build_hourly_brief(feed: dict[str, Any], feed_age_seconds: float | None) -> str:
    summary = feed.get("summary") or {}
    signals = [row for row in (feed.get("signals") or []) if isinstance(row, dict)]
    flows = [row for row in (feed.get("flow") or []) if isinstance(row, dict)]
    targets = [row for row in (feed.get("targets") or []) if isinstance(row, dict)]
    long_total = sum(max(0.0, as_float(row.get("value_long_usd"))) for row in signals)
    short_total = sum(max(0.0, as_float(row.get("value_short_usd"))) for row in signals)
    total = long_total + short_total
    if total > 0:
        bias = "LONG" if long_total >= short_total else "SHORT"
        share = max(long_total, short_total) / total
        positioning = f"Positioning: {bias} {share * 100:.0f}% by value ({money(long_total)} long / {money(short_total)} short)"
    else:
        positioning = "Positioning: warming up — no signed totals yet"
    lines = [
        "🧭 Copycat hourly intelligence brief",
        utc_label(),
        f"Cohort: {as_int(summary.get('live_wallets') or summary.get('selected_wallet_count')):,} live · {as_int(summary.get('qualified_wallets')):,} qualified · data {str(summary.get('data_quality_status') or 'unknown').lower()}",
        positioning,
    ]
    if feed_age_seconds is not None:
        lines.insert(3, f"Feed: {age_label(feed_age_seconds)}")
    if signals:
        lead = signals[0]
        value = signal_value(lead)
        lines.append(f"Lead conviction: {lead.get('coin', '?')} {signal_direction(value)} {abs(value) * 100:.0f}% · {signal_confidence(lead)}")
        runners = [f"{row.get('coin', '?')} {signal_direction(signal_value(row))} {abs(signal_value(row)) * 100:.0f}%" for row in signals[1:3]]
        if runners:
            lines.append("Next strongest: " + " · ".join(runners))
    positive = sorted([row for row in flows if as_float(row.get("net_value_flow_usd")) > 0], key=lambda row: as_float(row.get("net_value_flow_usd")), reverse=True)
    negative = sorted([row for row in flows if as_float(row.get("net_value_flow_usd")) < 0], key=lambda row: as_float(row.get("net_value_flow_usd")))
    if positive:
        row = positive[0]
        lines.append(f"Accumulation: {row.get('coin', '?')} +{as_int(row.get('net_buyer_count'))} net buyers · {signed_money(row.get('net_value_flow_usd'))}")
    if negative:
        row = negative[0]
        lines.append(f"Distribution: {row.get('coin', '?')} {as_int(row.get('net_buyer_count'))} net buyers · {signed_money(row.get('net_value_flow_usd'))}")
    allocations = sorted(targets, key=lambda row: abs(signed_target(row)), reverse=True)
    if allocations:
        lines.append("Model allocation: " + " · ".join(f"{row.get('coin', '?')} {signed_target(row) * 100:+.1f}%" for row in allocations[:3]))
    stories = [row for row in ((feed.get("market_narrative") or {}).get("stories") or []) if isinstance(row, dict)]
    if stories:
        lines.append("News watch:")
        for row in stories[:2]:
            title = " ".join(str(row.get("title") or "").split())
            if len(title) > 125:
                title = title[:122].rstrip() + "…"
            lines.append(f"• {row.get('source') or 'Market source'}: {title}")
            url = str(row.get("url") or row.get("link") or "").strip()
            if url:
                lines.append(url)
    events = [row for row in ((feed.get("catalyst_watch") or {}).get("events") or []) if isinstance(row, dict)]
    if events:
        row = sorted(events, key=lambda item: as_int(item.get("event_at_ms"), 2**62))[0]
        when = utc_label(row.get("event_at_ms")) if row.get("event_at_ms") else "time TBC"
        lines.append(f"Catalyst watch: {row.get('asset') or row.get('badge') or 'Market'} · {when} · {row.get('title')}")
    return "\n".join(lines)

def collect_alerts(feed_path: Path, feed: dict[str, Any], state: dict[str, Any], env: dict[str, str]) -> list[str]:
    now = time.time()
    now_ms = int(now * 1000)
    summary = feed.get("summary") or {}
    signals = [row for row in (feed.get("signals") or []) if isinstance(row, dict)]
    flows = [row for row in (feed.get("flow") or []) if isinstance(row, dict)]
    targets = [row for row in (feed.get("targets") or []) if isinstance(row, dict)]
    orders = [row for row in (feed.get("orders") or []) if isinstance(row, dict)]
    alerts: list[str] = []
    first_observation = not bool(state.get("baseline_seeded"))

    if not state.get("started_sent"):
        alerts.append("Copycat Telegram intelligence is now watching ✅\nOne hourly brief, plus meaningful cohort, order, news and catalyst triggers.")
        state["started_sent"] = True

    feed_age_seconds: float | None = None
    stale_minutes = max(1, as_int(env.get("COPYCAT_TELEGRAM_STALE_MINUTES"), 10))
    try:
        feed_age_seconds = max(0.0, now - feed_path.stat().st_mtime)
        was_stale = bool(state.get("feed_was_stale"))
        if feed_age_seconds > stale_minutes * 60 and not was_stale:
            alerts.append(f"⚠️ Copycat feed looks stale: dashboard-feed.json is {int(feed_age_seconds // 60)} minutes old.")
            state["feed_was_stale"] = True
        elif feed_age_seconds <= stale_minutes * 60:
            if was_stale:
                alerts.append("✅ Copycat feed freshness recovered.")
            state["feed_was_stale"] = False
    except Exception as exc:
        alerts.append(f"⚠️ Could not check Copycat feed freshness: {exc}")

    quality = str(summary.get("data_quality_status") or "unknown").lower()
    previous_quality = str(state.get("last_data_quality_status") or "")
    if quality != previous_quality:
        if quality not in {"healthy", "ok"}:
            alerts.append(f"⚠️ Copycat data quality: {quality}\n{summary.get('data_quality_message') or 'Dashboard data quality needs attention.'}")
        elif previous_quality and previous_quality not in {"healthy", "ok"}:
            alerts.append("✅ Copycat data quality recovered.")
        state["last_data_quality_status"] = quality

    brief_interval = max(5, as_int(env.get("COPYCAT_TELEGRAM_BRIEF_INTERVAL_MINUTES"), 60)) * 60
    last_brief = as_float(state.get("last_brief_sent_at"))
    if not last_brief or now - last_brief >= brief_interval:
        alerts.append(build_hourly_brief(feed, feed_age_seconds))
        state["last_brief_sent_at"] = now

    cooldown = max(5, as_int(env.get("COPYCAT_TELEGRAM_EVENT_COOLDOWN_MINUTES"), 60)) * 60
    event_times = state.get("last_event_sent_at")
    if not isinstance(event_times, dict):
        event_times = {}
    trigger_count = 0
    max_triggers = max(1, as_int(env.get("COPYCAT_TELEGRAM_MAX_TRIGGER_ALERTS"), 4))

    def add_trigger(message: str, key: str) -> bool:
        nonlocal trigger_count
        if first_observation or trigger_count >= max_triggers:
            return False
        previous = as_float(event_times.get(key))
        if previous and now - previous < cooldown:
            return False
        alerts.append(message)
        event_times[key] = now
        trigger_count += 1
        return True

    min_buyers = max(1, as_int(env.get("COPYCAT_TELEGRAM_FLOW_MIN_NET_BUYERS"), 5))
    min_flow = max(0.0, as_float(env.get("COPYCAT_TELEGRAM_FLOW_MIN_NET_VALUE_USD"), 1_000_000))
    previous_flows = state.get("last_flow_snapshot")
    if not isinstance(previous_flows, dict):
        previous_flows = {}
    current_flows: dict[str, dict[str, Any]] = {}
    for row in flows:
        coin = str(row.get("coin") or "").upper()
        if not coin:
            continue
        buyers = as_int(row.get("net_buyer_count"))
        value = as_float(row.get("net_value_flow_usd"))
        direction = 1 if buyers >= min_buyers and value >= min_flow else (-1 if buyers <= -min_buyers and value <= -min_flow else 0)
        current_flows[coin] = {"buyers": buyers, "value": value, "direction": direction}
        previous = previous_flows.get(coin) if isinstance(previous_flows.get(coin), dict) else {}
        old_direction = as_int(previous.get("direction"))
        old_value = abs(as_float(previous.get("value")))
        strengthened = direction and direction == old_direction and abs(value) >= max(min_flow, old_value * 1.5) and abs(buyers) >= abs(as_int(previous.get("buyers"))) + 2
        if direction and (direction != old_direction or strengthened):
            if direction > 0:
                add_trigger(f"🟢 Cohort accumulation: {coin}\nNet buyers: +{buyers}\nNet value flow: {signed_money(value)}", f"flow:{coin}:buy")
            else:
                add_trigger(f"🔴 Cohort distribution: {coin}\nNet buyers: {buyers}\nNet value flow: {signed_money(value)}", f"flow:{coin}:sell")
    state["last_flow_snapshot"] = current_flows

    previous_signals = state.get("last_signal_snapshot")
    if not isinstance(previous_signals, dict):
        previous_signals = {}
    shift = max(0.05, as_float(env.get("COPYCAT_TELEGRAM_SIGNAL_SHIFT"), 0.20))
    min_gross = max(0.0, as_float(env.get("COPYCAT_TELEGRAM_MIN_SIGNAL_GROSS_USD"), 500_000))
    current_signals: dict[str, dict[str, Any]] = {}
    for row in signals[:120]:
        coin = str(row.get("coin") or "").upper()
        if not coin:
            continue
        current = signal_value(row)
        gross = as_float(row.get("gross_value_usd")) or as_float(row.get("value_long_usd")) + as_float(row.get("value_short_usd"))
        current_signals[coin] = {"signal": current, "gross_value_usd": gross}
        previous = previous_signals.get(coin)
        old = maybe_float(previous.get("signal")) if isinstance(previous, dict) else maybe_float(previous)
        if old is not None and abs(current - old) >= shift and gross >= min_gross:
            add_trigger(f"⚡ Signal shift: {coin}\n{signal_direction(old)} {old * 100:+.0f}% → {signal_direction(current)} {current * 100:+.0f}%\nGross tracked value: {money(gross)}", f"signal:{coin}")
    state["last_signal_snapshot"] = current_signals

    previous_targets = state.get("last_target_snapshot")
    if not isinstance(previous_targets, dict):
        previous_targets = {}
    allocation_shift = max(0.01, as_float(env.get("COPYCAT_TELEGRAM_ALLOCATION_SHIFT"), 0.03))
    current_targets: dict[str, float] = {}
    for row in targets[:120]:
        coin = str(row.get("coin") or "").upper()
        if not coin:
            continue
        current = signed_target(row)
        current_targets[coin] = current
        old = maybe_float(previous_targets.get(coin))
        if old is not None and abs(current - old) >= allocation_shift:
            add_trigger(f"📊 Model allocation shift: {coin}\n{old * 100:+.1f}% → {current * 100:+.1f}%", f"allocation:{coin}")
    state["last_target_snapshot"] = current_targets

    order_threshold = max(0.0, as_float(env.get("COPYCAT_TELEGRAM_LARGE_ORDER_USD"), 250_000))
    seen_orders = list(state.get("seen_large_order_keys") or [])
    seen_order_set = set(seen_orders)
    for order in orders[:30]:
        key = order_key(order)
        if key in seen_order_set:
            continue
        value = abs(as_float(order.get("delta_value_usd") or order.get("notional_usd")))
        if first_observation or value < order_threshold:
            seen_orders.append(key)
            seen_order_set.add(key)
            continue
        wallet = order.get("wallet")
        url = f"https://hypurrscan.io/address/{wallet}" if isinstance(wallet, str) and wallet.startswith("0x") else ""
        message = f"🐋 Large Copycat order\n{order.get('side', '?')} {order.get('coin', '?')} · {money(value)}\nWallet: {order.get('wallet_label') or short_wallet(wallet)}"
        if url:
            message += f"\n{url}"
        if add_trigger(message, f"order:{key}"):
            seen_orders.append(key)
            seen_order_set.add(key)
    state["seen_large_order_keys"] = seen_orders[-500:]

    min_relevance = max(0.0, as_float(env.get("COPYCAT_TELEGRAM_NEWS_MIN_RELEVANCE"), 20))
    seen_stories = list(state.get("seen_story_keys") or [])
    seen_story_set = set(seen_stories)
    stories = [row for row in ((feed.get("market_narrative") or {}).get("stories") or []) if isinstance(row, dict)]
    stories.sort(key=lambda row: as_int(row.get("published_at_ms")), reverse=True)
    for story in stories:
        key = story_key(story)
        if key in seen_story_set:
            continue
        if first_observation or as_float(story.get("relevance_score")) < min_relevance:
            seen_stories.append(key)
            seen_story_set.add(key)
            continue
        title = " ".join(str(story.get("title") or "").split())
        if len(title) > 160:
            title = title[:157].rstrip() + "…"
        message = f"📰 New market headline · {story.get('source') or 'Market source'}\n{title}"
        url = str(story.get("url") or story.get("link") or "").strip()
        if url:
            message += f"\n{url}"
        if add_trigger(message, f"news:{key}"):
            seen_stories.append(key)
            seen_story_set.add(key)
            break
    state["seen_story_keys"] = seen_stories[-500:]

    seen_catalysts = list(state.get("seen_catalyst_keys") or [])
    seen_catalyst_set = set(seen_catalysts)
    events = [row for row in ((feed.get("catalyst_watch") or {}).get("events") or []) if isinstance(row, dict)]
    events.sort(key=lambda row: as_int(row.get("event_at_ms"), 2**62))
    for event in events:
        key = catalyst_key(event)
        if key in seen_catalyst_set:
            continue
        event_at = as_int(event.get("event_at_ms"))
        if first_observation or (event_at and event_at < now_ms - 15 * 60 * 1000):
            seen_catalysts.append(key)
            seen_catalyst_set.add(key)
            continue
        title = " ".join(str(event.get("title") or "").split())
        if len(title) > 160:
            title = title[:157].rstrip() + "…"
        asset = str(event.get("asset") or event.get("tracked_asset") or event.get("badge") or "Market")
        when = utc_label(event_at) if event_at else "time TBC"
        message = f"🗓️ New catalyst watch · {asset}\n{title}\nWhen: {when}"
        url = str(event.get("url") or event.get("link") or event.get("source_url") or "").strip()
        if url:
            message += f"\n{url}"
        if add_trigger(message, f"catalyst:{key}"):
            seen_catalysts.append(key)
            seen_catalyst_set.add(key)
            break
    state["seen_catalyst_keys"] = seen_catalysts[-500:]
    state["last_event_sent_at"] = {key: stamp for key, stamp in event_times.items() if now - as_float(stamp) < 7 * 24 * 60 * 60}
    state["baseline_seeded"] = True
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
        if not alerts:
            save_json(STATE_PATH, state)
            log("No Telegram alert conditions met.")
            return 0
        for text in alerts:
            send_telegram(token, chat_id, text)
            log("Sent Telegram alert: " + text.splitlines()[0])
        save_json(STATE_PATH, state)
        return 0
    except Exception as exc:
        log(f"Telegram alert failed: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

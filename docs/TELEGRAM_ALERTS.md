# Telegram intelligence alerts

The Telegram checker runs every five minutes so it can react quickly, but it only sends one scheduled intelligence brief per hour. Everything else is a meaningful, stateful trigger.

## What customers receive

### Hourly intelligence brief

The hourly message summarizes the exact data already used by the dashboard:

- live and qualified cohort size plus data quality
- long/short positioning by tracked value
- strongest conviction signals
- largest accumulation and distribution flow
- largest current model allocations
- the latest relevant market headlines
- the nearest catalyst on watch

### Trigger alerts

A separate alert is sent only when a configured condition is met:

- cohort accumulation or distribution reaches both the wallet-count and value-flow threshold
- a high-value signal changes materially
- a model allocation changes materially
- a genuinely large wallet order appears
- a new relevant news story enters Market Narrative
- a new event enters Catalyst Watch
- feed freshness or data quality degrades or recovers

Alerts are deduplicated and protected by per-event cooldowns. Candidate-universe and discovery milestone messages are disabled; those internal progress counters are not useful customer alerts.

## Recommended launch settings

Add these to \`publisher.env\` only when you want to override the conservative defaults:

\`\`\`text
COPYCAT_TELEGRAM_BRIEF_INTERVAL_MINUTES=60
COPYCAT_TELEGRAM_FLOW_MIN_NET_BUYERS=5
COPYCAT_TELEGRAM_FLOW_MIN_NET_VALUE_USD=1000000
COPYCAT_TELEGRAM_SIGNAL_SHIFT=0.20
COPYCAT_TELEGRAM_MIN_SIGNAL_GROSS_USD=500000
COPYCAT_TELEGRAM_ALLOCATION_SHIFT=0.03
COPYCAT_TELEGRAM_LARGE_ORDER_USD=250000
COPYCAT_TELEGRAM_EVENT_COOLDOWN_MINUTES=60
COPYCAT_TELEGRAM_NEWS_MIN_RELEVANCE=20
COPYCAT_TELEGRAM_MAX_TRIGGER_ALERTS=4
COPYCAT_TELEGRAM_STALE_MINUTES=10
\`\`\`

The Windows scheduled task should continue checking every five minutes. The script itself decides whether an hourly brief or a meaningful trigger should be sent, so the five-minute check does not create five-minute spam.

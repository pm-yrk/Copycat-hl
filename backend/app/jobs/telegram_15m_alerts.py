from __future__ import annotations

import json
import time

from app.platform_v1 import heartbeat, send_telegram_digest
from app.settings import get_settings


def main() -> None:
    settings = get_settings()
    sleep_seconds = max(60, int(getattr(settings, 'telegram_alert_interval_minutes', 15) or 15) * 60)
    while True:
        result = send_telegram_digest()
        print(json.dumps(result, indent=2, sort_keys=True))
        heartbeat('hwt-telegram-alerts-15m', result.get('status', 'ok'), '15m alert loop completed', {'sleep_seconds': sleep_seconds})
        time.sleep(sleep_seconds)


if __name__ == '__main__':
    main()

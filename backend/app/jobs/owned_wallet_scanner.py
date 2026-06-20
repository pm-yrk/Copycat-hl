from __future__ import annotations

import json
import logging
import os
import time

from app.owned_data import refresh_owned_scanner_batch
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def main() -> int:
    settings = get_settings()
    run_once = _truthy(os.getenv('OWNED_SCANNER_RUN_ONCE'))
    sleep_seconds = max(60, int(settings.owned_scanner_sleep_seconds or 3600))
    while True:
        started = time.time()
        try:
            result = refresh_owned_scanner_batch()
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
        except Exception:
            log.exception('owned wallet scanner batch failed')
        if run_once:
            return 0
        elapsed = time.time() - started
        wait = max(60, sleep_seconds - int(elapsed))
        log.info('owned wallet scanner sleeping %ss', wait)
        time.sleep(wait)


if __name__ == '__main__':
    raise SystemExit(main())

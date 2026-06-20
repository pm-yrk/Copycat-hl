from __future__ import annotations

import json
import os
import time

from app.copycat_data_lake import run_historical_fill_backfill


def main() -> None:
    loop = os.getenv('OWNED_BACKFILL_LOOP', 'true').lower() in {'1', 'true', 'yes', 'on'}
    sleep_seconds = int(float(os.getenv('OWNED_BACKFILL_SLEEP_SECONDS', '3600')))
    while True:
        print(json.dumps(run_historical_fill_backfill(), indent=2, sort_keys=True), flush=True)
        if not loop:
            break
        time.sleep(max(60, sleep_seconds))


if __name__ == '__main__':
    main()

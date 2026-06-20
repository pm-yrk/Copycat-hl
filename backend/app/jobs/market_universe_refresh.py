from __future__ import annotations

import json
import os
import time

from app.copycat_data_lake import quality_snapshot, refresh_market_universe_snapshot


def main() -> None:
    loop = os.getenv('MARKET_UNIVERSE_LOOP', 'true').lower() in {'1', 'true', 'yes', 'on'}
    sleep_seconds = int(float(os.getenv('MARKET_UNIVERSE_SLEEP_SECONDS', '60')))
    while True:
        result = refresh_market_universe_snapshot()
        try:
            result['quality'] = quality_snapshot()
        except Exception as exc:
            result['quality_error'] = str(exc)[:300]
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        if not loop:
            break
        time.sleep(max(15, sleep_seconds))


if __name__ == '__main__':
    main()

import os
import time
import traceback

from app.settings import get_settings
from app.worker import collect_once


def _interval_seconds() -> int:
    settings = get_settings()
    raw = os.getenv('COLLECTOR_INTERVAL_SECONDS') or str(settings.collector_interval_seconds)
    try:
        return max(10, int(float(raw)))
    except Exception:
        return 10


if __name__ == '__main__':
    interval = _interval_seconds()
    print(f'copycat collector loop starting; interval={interval}s', flush=True)
    while True:
        started = time.time()
        try:
            result = collect_once()
            print(result, flush=True)
        except Exception as exc:
            print(f'collector loop error: {exc}', flush=True)
            traceback.print_exc()
        elapsed = time.time() - started
        time.sleep(max(0, interval - elapsed))

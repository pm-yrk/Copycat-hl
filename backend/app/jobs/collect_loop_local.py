import time
from app.settings import get_settings
from app.worker import collect_once

if __name__ == '__main__':
    interval = get_settings().collector_interval_seconds
    while True:
        started = time.time()
        print(collect_once())
        time.sleep(max(0, interval - (time.time() - started)))

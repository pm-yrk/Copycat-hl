from __future__ import annotations

import logging
import os
import time

from app.database_diet import run_database_diet

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def main() -> None:
    result = run_database_diet()
    log.info('Database diet job result=%s', result)
    # Optional worker mode: keep service alive and prune repeatedly.
    sleep_seconds = int(float(os.getenv('COPYCAT_DATABASE_DIET_SLEEP_SECONDS', '0') or '0'))
    while sleep_seconds > 0:
        time.sleep(sleep_seconds)
        result = run_database_diet()
        log.info('Database diet job result=%s', result)


if __name__ == '__main__':
    main()

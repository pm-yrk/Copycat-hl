from __future__ import annotations

import json
import sys

from app.backtest import import_backtest_csv


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python -m app.jobs.import_backtest_csv /path/to/backtest.csv')
    print(json.dumps(import_backtest_csv(sys.argv[1]), indent=2, sort_keys=True))

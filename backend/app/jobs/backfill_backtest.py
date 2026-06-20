from __future__ import annotations

import json

from app.backtest import run_backtest


if __name__ == '__main__':
    print(json.dumps(run_backtest(), indent=2, sort_keys=True))

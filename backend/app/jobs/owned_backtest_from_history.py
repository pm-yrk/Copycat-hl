from __future__ import annotations

import json

from app.owned_backtest import run_owned_backtest_from_history


if __name__ == '__main__':
    print(json.dumps(run_owned_backtest_from_history(), indent=2, sort_keys=True))

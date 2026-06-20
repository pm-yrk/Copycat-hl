from __future__ import annotations

import json

from app.owned_data import owned_wallet_refresh


if __name__ == '__main__':
    print(json.dumps(owned_wallet_refresh(run_collection=True), indent=2, sort_keys=True))

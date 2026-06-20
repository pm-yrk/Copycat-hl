from __future__ import annotations

import json

from app.owned_data import seed_owned_candidates


if __name__ == '__main__':
    print(json.dumps({'seeded_or_existing_candidates': seed_owned_candidates()}, indent=2, sort_keys=True))

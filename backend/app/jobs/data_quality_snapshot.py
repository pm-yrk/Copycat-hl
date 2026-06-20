from __future__ import annotations

import json
from app.copycat_data_lake import quality_snapshot

if __name__ == '__main__':
    print(json.dumps(quality_snapshot(), indent=2, sort_keys=True))

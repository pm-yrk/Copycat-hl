from __future__ import annotations

import json

from app.platform_v1 import create_coverage_snapshot, ensure_platform_tables_once, heartbeat, platform_health


def main() -> None:
    ensure_platform_tables_once()
    cov = create_coverage_snapshot()
    heartbeat('hwt-copycat-platform-migrate', 'ok', 'Platform tables checked', cov)
    print(json.dumps({'status': 'ok', 'coverage': cov, 'health': platform_health()}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

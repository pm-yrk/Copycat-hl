# Copycat Platform V1

This build moves Copycat toward a dashboard + API + alerts product.

Core principle: use Hyperliquid-native data, own the derived intelligence, and label coverage honestly until the indexed universe is large enough to support stronger top-wallet claims.

Workers added:
- `python -m app.jobs.copycat_platform_migrate`
- `python -m app.jobs.telegram_15m_alerts`

Public endpoints added:
- `/api/data/v1/public/platform-health`
- `/api/data/v1/public/coverage-preview`
- `/api/data/v1/public/leaderboard-preview`
- `/api/data/v1/public/token-screener-preview`
- `/api/data/v1/public/asset/{coin}`
- `/api/data/v1/public/asset-details?symbols=BTC,ETH`
- `/api/data/v1/public/what-changed`

Option A data strategy: official Hyperliquid-native capture only. Historical coverage grows from data Copycat can collect and store.

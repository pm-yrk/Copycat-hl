# Copycat Big API Foundation Patch

This patch adds the first customer-facing Copycat Data API foundation:

- Hyperliquid perps market universe snapshots via official `metaAndAssetCtxs`.
- Token screener API and public preview.
- Leaderboard v2 API with richer scoring fields.
- Historical fill backfill worker using official `userFillsByTime` availability.
- Backfill coverage endpoints.
- Wallet universe endpoint.
- API access page redesign inspired by professional wallet/token screeners.

## Important data truth

This does **not** magically prove Copycat has every historical Hyperliquid wallet today. The official user fill API is limited to recent per-wallet data. Copycat will store everything it observes from now on and backfill the maximum recent per-wallet fills available from the official API. Full all-platform historical coverage requires either long-running collection or a lawful full historical data feed.

## New services recommended

### hwt-market-universe

Command:

```text
python -m app.jobs.market_universe_refresh
```

Env:

```text
DATABASE_URL = same as hwt-api
MARKET_UNIVERSE_SLEEP_SECONDS = 60
```

### hwt-historical-fill-backfill

Command:

```text
python -m app.jobs.historical_fill_backfill
```

Env:

```text
DATABASE_URL = same as hwt-api
OWNED_BACKFILL_WALLET_LIMIT = 25
OWNED_BACKFILL_DAYS = 365
OWNED_BACKFILL_MAX_PAGES_PER_WALLET = 5
OWNED_BACKFILL_MAX_SECONDS = 900
OWNED_BACKFILL_SLEEP_SECONDS = 3600
OWNED_DISCOVERY_FETCH_FILLS = false
```

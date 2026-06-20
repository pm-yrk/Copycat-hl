# Copycat owned wallet refresh operations

The scheduled `hwt-daily-refresh-midnight` job is not the live dashboard engine.

Live dashboard movement should come from:

- `hwt-live-events`
- `hwt-collector-live-10s`
- Hyperliquid live state / prices
- Copycat database snapshots

`hwt-daily-refresh-midnight` should only refresh owned wallet metrics and cohort selection. It should not run continuously or overlap with another manual trigger.

## Recommended Render environment

For `hwt-daily-refresh-midnight`:

```text
DATABASE_URL=same Supabase Postgres URL as hwt-api
WALLET_DISCOVERY_PROVIDER=owned
OWNED_DISCOVERY_REFRESH_LIMIT=500
OWNED_REFRESH_LIMIT=75
OWNED_REFRESH_MAX_SECONDS=600
OWNED_REFRESH_RUN_COLLECTION=false
OWNED_DISCOVERY_FETCH_FILLS=false
```

`OWNED_DISCOVERY_REFRESH_LIMIT` can stay high because it is the universe cap. The scheduled cron uses `OWNED_REFRESH_LIMIT` so the cron stays bounded.

Set `OWNED_DISCOVERY_FETCH_FILLS=true` only for a separate deeper historical enrichment job. It can be slower because `userFillsByTime` can be heavy for active wallets.

## What the log should look like

Healthy logs should show:

```text
Owned wallet metrics 1/75 start ...
Owned wallet metrics 1/75 done ...
Owned wallet metrics 2/75 start ...
...
```

If a run is already active, a second trigger should exit cleanly:

```text
another owned wallet refresh is already running
```

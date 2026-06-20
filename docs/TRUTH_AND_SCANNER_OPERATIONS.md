# Copycat Truth Layer and Owned Wallet Scanner

This build keeps the live dashboard honest while Copycat's own Hyperliquid-native universe grows.

## What the dashboard may claim now

Until the owned scanner has indexed enough wallets, the product should say:

> Top 50 Copycat-ranked wallets from our indexed Hyperliquid wallet universe.

It should not claim:

> Top 50 most profitable wallets on all of Hyperliquid.

The default guard is `OWNED_TOP_CLAIM_MIN_INDEXED_WALLETS=10000`. The dashboard and API expose `top_claim_ready` so the wording can change only when the indexed universe is broad enough.

## New worker

Service name:

```text
hwt-owned-wallet-scanner
```

Command:

```text
python -m app.jobs.owned_wallet_scanner
```

Recommended environment:

```text
DATABASE_URL = same as hwt-api
WALLET_DISCOVERY_PROVIDER = owned
OWNED_SCANNER_BATCH_SIZE = 250
OWNED_SCANNER_MAX_SECONDS = 900
OWNED_SCANNER_SLEEP_SECONDS = 3600
OWNED_TOP_CLAIM_MIN_INDEXED_WALLETS = 10000
OWNED_DISCOVERY_FETCH_FILLS = false
```

The scanner processes the known candidate universe in least-recently-indexed order. It is separate from the live dashboard and daily refresh so large scans do not block page speed.

## New endpoints

```text
/api/dashboard-consistency
/api/data/v1/status
```

`/api/dashboard-consistency` checks whether the current dashboard is synced, whether recent-order assets are mapped, whether Nansen is off for the live path, and whether live wallet coverage is healthy.

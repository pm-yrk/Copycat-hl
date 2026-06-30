# Copycat owned Hyperliquid data engine

Copycat now has a Hyperliquid-native wallet refresh path for the live product.

## What it does

- Keeps the existing wallet universe as the seed set.
- Stores Hyperliquid-native wallet fills in `owned_wallet_fills`.
- Stores latest wallet ranking metrics in `owned_wallet_metrics`.
- Stores historical ranking snapshots in `owned_wallet_metric_history`.
- Selects the active Copycat wallet cohort from our own stored metrics.
- Leaves the existing cohort live if too few owned wallets pass validation.
- Builds future backtests from our own stored fills/metric history when enough history exists.

## What it does not do

It does not fabricate a 1-year backtest. Historical rows can only be produced after enough owned history exists, or from a separately validated import.

## Render jobs

- `hwt-daily-refresh-midnight` now runs `python -m app.jobs.owned_wallet_refresh`.
- `hwt-backtest-weekly` now runs `python -m app.jobs.owned_backtest_from_history`.

Neither job needs LegacyExternalProvider credits.

## Optional seed wallets

Set `OWNED_DISCOVERY_SEED_WALLETS` to a comma/newline separated list of wallet addresses if you want to add wallets manually without LegacyExternalProvider.

## Important

LegacyExternalProvider can remain in the code as an optional emergency/manual source, but the scheduled live product path is now Hyperliquid-native.

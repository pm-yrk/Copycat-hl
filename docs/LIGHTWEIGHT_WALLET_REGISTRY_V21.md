# Copycat Lightweight Wallet Registry v2.1

This adds a local SQLite wallet database on the PC.

## Goal

Build a growing wallet registry without storing huge raw trade history.

## Storage

The local database is written to:

```text
copycat_wallet_registry/copycat_wallet_registry.sqlite
```

Exports are written to:

```text
copycat_wallet_registry/exports
```

The database and exports are ignored by Git.

## What gets stored per wallet

Only essential summary data:

- wallet address
- first seen time
- last seen time
- discovery count
- source list
- last scanned time
- scan count
- account value
- withdrawable
- open position count
- position value
- unrealized PnL
- fills count
- active symbols
- closed PnL
- wins
- losses
- win rate
- Copycat score
- qualified yes/no
- last error

Raw fills are not permanently stored.

## Jobs

Hourly discovery:

```bat
scripts\wallet_registry\install_hourly_wallet_discovery_task.cmd
```

Daily scoring at 06:00 local time:

```bat
scripts\wallet_registry\install_daily_wallet_scoring_task_0600.cmd
```

Manual 500-wallet score run:

```bat
scripts\wallet_registry\score_wallets_now_500.cmd
```

Open exports:

```bat
scripts\wallet_registry\open_registry_exports.cmd
```

## Safety

This does not change live publisher wallets automatically.

Manual application requires:

```bat
scripts\wallet_registry\apply_registry_top50_to_publisher_REQUIRES_YES.cmd
```

That command requires typing `YES` and creates a backup first.

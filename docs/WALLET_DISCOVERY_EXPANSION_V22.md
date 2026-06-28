# Copycat Wallet Discovery Expansion v2.2

This expands the wallet discovery pipeline.

It scans:
- Copycat result folders
- `C:\CopycatSnapshotPublisher`
- `Downloads`
- `C:\CopycatArchive`
- old patch zip files
- saved leaderboard/export files
- imported text/CSV/HTML/JSON files
- small configured public URL sources

## Important limitation

This does not magically pull every Hyperliquid wallet. Official free endpoints generally need a wallet address before they can return user-specific data.

To grow quickly, add real wallet-address source files into:

```text
copycat_wallet_registry\imports
```

## Commands

```bat
scripts\wallet_registry\discover_expanded_now.cmd
scripts\wallet_registry\open_wallet_imports_folder.cmd
scripts\wallet_registry\open_public_wallet_sources.cmd
scripts\wallet_registry\install_hourly_expanded_discovery_task.cmd
scripts\wallet_registry\status_discovery_v22.cmd
```

## Safety

This only discovers wallet addresses.

It does not:
- score every wallet immediately
- change live publisher wallets
- push to GitHub
- edit dashboard design

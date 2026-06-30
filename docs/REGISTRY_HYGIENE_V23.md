# Copycat Registry Hygiene v2.3

This keeps the local wallet registry cleaner.

## What it does

It removes obvious non-trader addresses from the local SQLite registry:

- zero address
- burn/placeholder addresses
- all-one-character addresses such as all `f` or all `2`
- Hyperliquid/system-style `0x200000000000000000000000000000000000....` addresses
- known token contracts such as Ethereum USDC

## Commands

Preview only:

```bat
scripts\wallet_registry\preview_registry_hygiene_now.cmd
```

Clean registry:

```bat
scripts\wallet_registry\clean_registry_hygiene_now.cmd
```

Then check status:

```bat
scripts\wallet_registry\status_discovery_v22.cmd
```

## Safety

This only touches:

```text
copycat_wallet_registry\copycat_wallet_registry.sqlite
```

It does not change:

- live publisher wallets
- Cloudflare
- dashboard frontend
- GitHub main

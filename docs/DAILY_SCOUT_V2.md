# Copycat Daily Scout v2

Daily Scout v2 is a safe local scanner that expands the wallet universe above the live dashboard's 50 tracked wallets.

## What it does

- Discovers candidate wallet addresses from local project files, the live publisher wallet list, optional `candidate_wallets.txt`, and public Hyperliquid vault summaries when available.
- Scans up to 500 wallets per run by default.
- Uses a slow API delay of 2.5 seconds per wallet.
- Scores wallets using account value, fills, open positions, realized/closed PnL where available, active symbols, and win/loss data where available.
- Writes local recommendations to `copycat_daily_scout_out_v2/latest`.

## What it does not do

- It does not change the live Snapshot Publisher automatically.
- It does not push to GitHub.
- It does not upload anything to Cloudflare R2.
- It does not claim to identify the top 50 wallets across all Hyperliquid.

## Default schedule

The included installer creates a Windows Scheduled Task at 06:00 local computer time.

## Safe run commands

From the repo root:

```bat
scripts\daily_wallet_scout_v2\run_daily_scout_v2_now_500.cmd
```

Install scheduled daily run:

```bat
scripts\daily_wallet_scout_v2\install_daily_scout_task_0600.cmd
```

Open latest results:

```bat
scripts\daily_wallet_scout_v2\open_latest_scout_results.cmd
```

## Manual live apply

Only after reviewing the output, you can manually apply the recommended top 50 to the live publisher using:

```bat
scripts\daily_wallet_scout_v2\apply_latest_top50_to_publisher_REQUIRES_YES.cmd
```

That command requires typing `YES` and creates a backup of the old publisher wallet list.

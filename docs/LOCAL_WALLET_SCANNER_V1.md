# Copycat local wallet scanner v1

This scanner runs locally on the laptop and does not use Supabase.

What it does:

1. Reads public Hyperliquid `recentTrades` for a small basket of liquid coins.
2. Extracts trader wallet addresses from the `users` field.
3. Merges those addresses with the existing `wallets.txt` and `candidate_wallets.txt`.
4. Fetches Hyperliquid `clearinghouseState` for candidates.
5. Scores wallets using visible account value, open exposure, recent trade activity, position diversity, and unrealized PnL.
6. Optionally updates `wallets.txt` with the top selected wallets.

What it does not claim yet:

- It is not a full historical profit audit.
- It is not proof of the top 50 most profitable wallets across all Hyperliquid.
- It is a local, free-mode scanner for improving the Copycat candidate universe.

Recommended cadence:

- Run manually first with `run_local_scanner_once.cmd`.
- If results look good, run `run_local_scanner_update_wallets.cmd`.
- Let the snapshot publisher continue running; it reloads `wallets.txt` each cycle.

Output files:

- `scripts/local_snapshot_publisher/scanner_state/scanner_results.json`
- `scripts/local_snapshot_publisher/scanner_state/top_wallets.txt`
- `scripts/local_snapshot_publisher/candidate_wallets.txt`

Useful knobs via CMD before running:

```cmd
set SCANNER_MAX_CANDIDATES=160
set SCANNER_SELECTED_WALLETS=50
set SCANNER_COINS=BTC,ETH,SOL,HYPE,XRP,DOGE,SUI,LINK,AVAX,BNB
```

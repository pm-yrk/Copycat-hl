# Copycat local snapshot publisher

This publisher lets Copycat run in free snapshot mode:

```text
Hyperliquid public API → your laptop → compact JSON snapshots → Cloudflare R2 → Cloudflare Pages dashboard
```

It does not use Supabase, does not store large history locally, and overwrites the same small JSON files each run.

## Files it uploads

- `dashboard-feed.json`
- `dashboard-tick.json`
- `performance-index.json`
- `token-icons.json`
- `api/leaderboard-preview.json`
- `api/token-screener-preview.json`
- `api/coverage-preview.json`
- `api/platform-health.json`
- `api/status.json`

## Setup

1. Create an R2 API token with Object Read & Write access to `copycat-snapshots`.
2. Run `scripts/local_snapshot_publisher/install_snapshot_publisher.cmd`.
3. Edit `scripts/local_snapshot_publisher/publisher.env`.
4. Run `scripts/local_snapshot_publisher/run_snapshot_publisher_once.cmd`.
5. Open the R2 public URL for `dashboard-feed.json` and confirm it updated.
6. Run `scripts/local_snapshot_publisher/run_snapshot_publisher_loop.cmd` to keep publishing every minute.

## Storage use

The script keeps a local copy in `copycat_snapshot_out` and overwrites it. Normal storage usage should remain tiny.

## Important

The seeded `wallets.txt` only contains wallets present in the current public snapshot. Add more Copycat-ranked wallets later for better coverage.

# Copycat free-mode site parity

This patch converts public-facing read-only pages to Cloudflare/R2 snapshot mode while Render and Supabase are suspended.

## What works in strict free mode

- Dashboard from `dashboard-feed.json` and `dashboard-tick.json`
- Copycat Index from `performance-index.json`
- API preview page from `/api/*.json` snapshot files
- Ranking audit preview from `api/ranking-audit.json`
- Free-mode audit/status from `api/audit.json`, `api/free-mode-status.json`, and `api/scanner-status.json`

## What is intentionally disabled or softened

- Supabase login/auth/paywall
- Private API keys
- Dynamic database-backed queries
- Full historical wallet/backtest explorer
- Hosted always-on Render workers

## Data claim

The displayed data is correct for the currently selected locally scanned wallet universe at the time the publisher generated the snapshot. It is not yet a verified all-Hyperliquid top-50 profit ranking.

The index is stored locally in `scripts/local_snapshot_publisher/scanner_state/performance_index_state.json`, published locally to `copycat_snapshot_out/performance-index.json`, and uploaded publicly to R2 as `performance-index.json`.

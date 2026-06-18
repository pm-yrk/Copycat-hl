# Copycat light/dark design patch

This patch updates the Copycat frontend with the approved dark design and a Financial-Times-inspired light mode.

Included:
- Copycat wordmark only, no CC corner logo
- Dark and light theme support with a small nav toggle
- Premium landing, pricing, login, and dashboard styling
- Dashboard positioning-bias LONG/SHORT toggle
- Most recent orders panel
- Token-style asset icons in signal and flow tables
- Flowing Hyperliquid-green line backgrounds across all pages
- Docker npm install fix retained
- Backend `/api/recent-orders` endpoint derived from latest position changes

Apply with robocopy into the existing `hyper_wallet_tracker_saas_v1` repo, commit, push, then redeploy API and frontend on Render.

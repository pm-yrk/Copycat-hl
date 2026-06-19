Copycat ranking + insight polish patch

Includes:
- Ranking V2 backend scoring: positive real PnL only, no volume-as-PnL fallback, ROI, consistency, drawdown, account size, activity and anti-fluke scoring.
- Private /api/ranking-audit and /ranking-audit page for checking the active top-50 wallet cohort.
- /api/signal-explain endpoint for per-asset wallet-contributor explainability.
- /api/insights endpoint and dashboard “At a glance” rail.
- Dashboard data-quality badge with pulsing green indicator.
- Token icon presentation cleaned up: no cheap circular chip background around logos.
- Recent-orders card pulled together with the right-side insight/data-quality rail.

After deployment, run the daily refresh once to rebuild the active top 50 using Ranking V2.

# Copycat Live Strategy Index patch

This patch fixes the frontend build error caused by `lib/api.ts` importing a removed `supabase` export, then adds the Copycat Live Strategy Index.

What it adds:
- Public `/api/performance-index` endpoint.
- `/api/performance-index/audit` sanity-check endpoint.
- Automatic `strategy_index_points` table creation.
- Copycat Index starting at 100 with no hindsight backfill.
- BTC and ETH benchmark lines.
- Homepage live index widget replacing the fake hero chart.
- Dashboard/deep performance widget.
- `/performance` page for testing the deeper index view.

Method:
- Uses latest published Copycat portfolio targets.
- Marks the model against live Hyperliquid `allMids` prices.
- Persists index points at most once per minute.
- Adds a 15 bps fee/slippage buffer on rebalance turnover.
- Shows a live non-persisted mark between stored points.

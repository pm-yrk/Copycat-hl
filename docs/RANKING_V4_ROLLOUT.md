# Ranking V4 / index V3: guarded rollout

Status: implemented behind an activation manifest; NOT activated on the live PC.
No frontend files, pricing, payments or customer accounts are changed by this patch.

The expanded 250-wallet public portfolio review completed with no endpoint errors.
65 pass the portfolio-only filters; exclusions were 73 nonpositive recent/long-term
PnL, 61 below minimum equity, 43 overly sparse histories and 8 short histories.
This is not 65 fully qualified live candidates: fresh fill/funding verification
on Windows is still required. Captures span 5–6 October and are not simultaneous.
34 offline regression tests and both legacy worker/selector self-tests pass.

## One Windows preparation command

From Command Prompt:

```cmd
cd /d C:\dev\hyper_wallet_tracker_saas_v1 && git pull --ff-only origin main && py -3 scripts\wallet_registry\prepare_ranking_v4.py --limit 500
```

This refreshes up to 500 prioritised candidates using actual fills, funding,
account state and perpetual portfolio histories. It can take several hours.
Leave the computer awake. Successful scans are stored immediately; rerunning
skips records whose metrics AND portfolio evidence remain fresh. Rate limits
stop the batch safely rather than causing an unlimited retry loop.

The command writes `Copycat-v4-review-TIMESTAMP.zip` to Downloads. It does not
install an activation manifest, reset an index, replace wallets.txt, or change
scheduled tasks. Existing scheduled ranking jobs can still consume refreshed
metrics under their existing methodology. A ZIP containing a review is not
confirmation of activation. Fewer than 50 qualifiers means SAFE HOLD.

## Ranking definition and limits

The existing complete-fill/activity gates remain required. Both trade metrics
and portfolio evidence must be at most 24 hours old. Accounts need positive
perpetual PnL over the returned roughly-month window and a window beginning at
the last observed point at/before 90 days ago (at most 98 days total). Actual
coverage is retained; no exact 90-day sample is invented by interpolation.

Score components: 35% longer-window dollar profit/day percentile, 25% recent
dollar profit/day percentile, 20% positive sampled intervals, 15% sampled
profit/drawdown recovery, 5% concentration of positive interval gains.
These are transparent heuristic weights, not empirically proven optimal weights.
This is NOT ROI, Sharpe, exact time-weighted return or guaranteed future profit.
Larger profitable accounts can score higher because dollar profitability is a
deliberate component. Sampled drawdown misses excursions between observations.
Portfolio-only review results cannot replace fresh independent trade evidence.
The prioritised sample is not an exhaustive fresh ranking of every indexed wallet.

## New index engine

- Exactly 50 unique, live wallet states are required before rebalancing.
- Equal wallet budgets; a wallet's whole position book is scaled proportionally
  if its gross notional exceeds its equity. Idle budgets are retained.
- Opposing exposures cancel. Net exposures are NOT scaled back up to 100%.
- Individual assets are capped at 25%; excess stays unallocated, not redistributed.
- `UNALLOCATED` in the allocation payload is model collateral, not observed USDC
  holdings. It prevents existing allocation renderers from magnifying exposure.
- Prior holdings earn price changes. There is no arbitrary +/-8% return clamp.
- A 15bp buffer is charged on traded notional after inception. The initial setup
  is normalised to 100; this excludes initial entry costs. Funding is excluded and
  explicitly reported as excluded. This is a model, not actual wallet returns.
- Missing prices, incomplete/stale states and insolvent model equity block updates.
  Previous public data can remain available but must retain its original timestamp.
- New series use a separate SQLite journal; state and chart points commit together.
  Retries do not double-charge fees. Restarts cannot reset an existing series.
- The SP500 comparison remains the Hyperliquid Trade[XYZ] perpetual benchmark.

## Activation requirements (not executed)

1. Obtain a freshly generated V4 report with 50 fully qualified wallets from the
   Windows preparation scan, and review its actual coverage/exclusions.
2. Confirm the active publisher's configured legacy state/history paths, pause
   the publisher for a coherent final archive, and run `prepare_index_restart.py`
   with explicit `--report`, `--legacy-state`, `--legacy-history` and `--output`.
   It copies state and backs up SQLite including committed WAL pages, checks
   integrity, records checksums, and writes a PREPARED manifest outside live paths.
3. Deploy the tested publisher and its `performance_index_v3.py` module together.
   Only after verification install the prepared manifest as
   `scanner_state/index_activation.json` in the active publisher directory.
   The manifest's wallet list is authoritative to avoid mixed-cohort publication.
4. Restart the publisher and verify an actual complete capture: correct series ID,
   50 wallets, inception at 100, allocation including collateral, all benchmarks,
   timestamps, costs and history. A prepared archive is not a successful reset.
5. Check a subsequent capture and a process restart preserve inception/history.
   Existing ranking jobs detect the manifest and use V4 thereafter. Membership
   changes retain the series ID, so re-ranking does not restart performance.

The legacy series is never overwritten by the new journal. If activation has not
occurred, ordinary publisher runs continue on the old method and old series.

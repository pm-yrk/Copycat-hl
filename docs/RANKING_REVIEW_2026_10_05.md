# Ranking correction: evidence and activation status

Review input: user-supplied ranking metrics export, 5 October 2026 17:01 UTC.
No credentials or original database records are included in this repository.

## Reproduced findings

- 91,568 wallet records; 91,323 score-ready; 89,330 marked history-complete.
- Applying the current qualification rules at the export time produces 57
  eligible wallets. 79,582 complete records fail the seven-day freshness rule.
- The reconstructed first-ranked wallet has approximately $283,812 realised
  net profit and $9,893 current equity. The current formula reports 2,869%
  ROI; this is a profit/current-equity ratio, not a validated period return.
- Ten of the reconstructed top 50 have reported gross positions greater than
  ten times current equity. This is a risk observation, not proof of losses.
- These reconstructed rankings are not proof of the active publisher cohort.

## Implemented first stage

The profit-history worker now reserves alternating non-member scan opportunities
for stale, previously profitable challengers. Active members retain priority;
new discovery continues. Two regression tests verify these properties.
Deployment requires the Windows worker to load the updated code.

The read-only collect_ranking_evidence.py command collects portfolio history and
current perp state for active members, current leading qualifiers and historical
challengers (250 total by default). Historical scores only prioritise collection;
their stale timestamps never become eligible live evidence. It writes a ZIP in
Downloads and changes no database records, cohort or index state.

## Outstanding before activation

The supplied metrics are aggregates: they cannot reconstruct capital flows,
unrealised performance, a time-weighted return curve or actual peak-to-trough
drawdown. Inspect fresh portfolio evidence before choosing a replacement formula.
If sampled portfolio history cannot resolve deposits and withdrawals precisely,
collect ledger events and report approximation/coverage explicitly.

Validate corrected selection and portfolio construction independently, including
missing prices, publishing gaps, trading costs and funding. Preserve the old
index state and historical archive. A new series starts at 100 only at successful
activation, with a new series identifier and visible methodology/start date;
ordinary restarts must not reset it. No reset or replacement ranking has been
activated by these patches.

## Follow-up review, 5 October 2026 21:21 UTC

The active cohort was fetched from the public ranking audit, rather than inferred
from the exported database. All 50 active addresses had fresh public portfolio
and clearinghouse-state evidence collected in this run. Across their returned
perpMonth periods (actual timestamps retained, roughly one month):

- 25/50 have negative PnL changes.
- The sum of the 50 changes is approximately -$972,736.
- Their current open unrealised PnL totals approximately -$1,033,935.

The last two quantities are separate; do NOT add them together. Neither is the
Copycat Index return. These are observational results from asynchronous public
snapshots, not a simulated portfolio backtest or a prediction.

The replacement scorer in performance_top50_v4.py is SHADOW ONLY. It compares
profit per actual observed day across recent and approximately 90-day perpetual
windows, with sampled consistency, drawdown recovery and gain-concentration
components. It does not use profit/current balance as ROI. Its heuristic weights
are unvalidated; it is not exposed as the live selector. It intentionally cannot
activate a cohort. Fresh independent trade-history qualification is still needed.

Additional backend fixes implemented:

- Inclusive fill pagination with deduplication and explicit completeness;
  use unaggregated fills to detect the 10,000-fill API ceiling reliably.
- Paginated funding history; failed or stalled history cannot be complete.
- Invalid account/history response shapes fail instead of becoming zero values.
- API errors preserve good metrics and their original observation time, record
  the failure separately and back off the failing wallet for 30 minutes.
- Funding-only days no longer count as active trading days.
- Each successful scan stores raw perpetual portfolio evidence in SQLite, in
  the same transaction as its metrics.
- Preview ranking runs no longer overwrite live report/scanner/flag files.
- Future-dated metrics fail freshness eligibility.
- Evidence collection checkpoints every endpoint and resumes after interruption.

Fourteen offline regression tests plus the worker and selector self-tests pass.
This patch does not change frontend files, publish a new cohort, reset the index,
or deploy code onto the user's Windows scanner. The remaining activation work
includes a fresh broad challenger scan, validated live selection, correction of
the index's allocation amplification and per-update return clamp, and an archived,
versioned one-time index restart. Preserve the old performance series.

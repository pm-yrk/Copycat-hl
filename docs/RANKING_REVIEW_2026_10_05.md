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
implemented or activated by this first-stage patch.

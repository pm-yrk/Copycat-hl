# Copycat dashboard data accuracy + allocation polish patch

Changes:
- Removes horizontal scrolling and outline boxes from the portfolio allocation legend.
- Adds a short description under the donut explaining the allocation index.
- Aligns customer-facing Signal % with value-weighted long/short exposure so At a glance, Signal Board, and Long vs Short are consistent.
- Fixes buyer/seller pressure reads so Accumulation/Distribution follows net value flow, not only wallet count.
- Adds Most traded asset to At a glance.
- Adds Largest account under Tracked account value.
- Extends the audit checks for display-signal and flow-direction consistency.
- Keeps dashboard polling at 1 second.

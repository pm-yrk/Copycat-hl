# Copycat data consistency + visual polish patch

Fixes dashboard data consistency by making summary metrics use the same completed asset_signals snapshot as the signal/flow tables. Also aligns new signal timestamps to the positions batch timestamp going forward, improves recent order deltas with full outer join, adds /api/data-health, fixes the short bias label, and softens the page background edges.

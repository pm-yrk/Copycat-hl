# Copycat live UI + order label patch

Fixes requested:
- Forces USDC/CASH to display as USDC and uses the correct blue USDC icon locally.
- Rounds long/short exposure and signal percentages to whole percentages.
- Makes dashboard API reads cache-busted and polls the UI every 3 seconds.
- Adds backend no-cache headers for all `/api/*` responses.
- Improves recent-orders labels: Open long, Add long, Reduce long, Close long, Open short, Add short, Reduce short, Close short.
- Moves the positioning bias pill down closer to the KPI bubbles.

Note: the dashboard can only show new live data after the collector has written a fresh snapshot. The frontend now checks every 3 seconds; your collector should still run every 10 seconds.

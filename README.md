# Copycat live 1-second data patch

This patch makes the dashboard check the API every 1 second and changes the collector from a scheduled/slow refresh into a continuously running live worker.

What changes:
- Dashboard poll interval: 1 second.
- Footer text: page checks every 1s.
- Collector loop minimum interval: 1 second.
- Render worker env: COLLECTOR_INTERVAL_SECONDS=1.
- Parallel wallet collection workers: default 30, max 50.

Important: this does not fake movement. The page checks every second, but values only change when the backend has written a fresh wallet/position snapshot. If a full 50-wallet Hyperliquid fetch takes 3-8 seconds, the screen will update as soon as that completed batch arrives.

# copycat.hl parallel collector freshness fix

Keeps the UI unchanged.

Changes:
- Collects the active 50-wallet cohort concurrently instead of one wallet at a time.
- Writes one completed batch with one timestamp, preserving data correctness.
- Refuses to publish a new signal snapshot if fewer than 90% of wallets collect successfully.
- Audit freshness now checks the latest completed `collect_once` run.

Redeploy `hwt-api` and `hwt-collector-live-10s`, then wait for one full collector cycle and rerun `/audit`.

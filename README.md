# Copycat active-cohort data fix

Fixes the audit failure where `Tracked account value consistency` could fail because signal calculations included historical wallet snapshots from retired/previous cohorts.

Changes:
- `worker.py`: signal calculations now use only the current active 50 qualified wallets.
- `worker.py`: current/lookback position rows are restricted to the same active cohort.
- `main.py`: summary/audit rollups are restricted to active wallets.

After deploying, let the 10-second collector complete one full cycle, then rerun `/audit`.

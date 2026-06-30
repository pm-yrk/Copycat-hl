# Operations runbook

## Normal system behavior

Every 15 minutes:

```bash
python -m app.jobs.collect_once
```

Every midnight:

```bash
python -m app.jobs.daily_refresh
```

## Daily checks

Check the latest run table in the dashboard. You want recent successful rows for:

- `collect_once`
- `compute_signals`
- `daily_refresh`

## If customers say the dashboard is stale

1. Check `collector_runs`.
2. Check the hosting cron job logs.
3. Run `python -m app.jobs.collect_once` manually.
4. If LegacyExternalProvider is failing, the existing qualified-wallet list can still be collected until the daily refresh issue is fixed.

## If alerts are too noisy

Increase:

```text
ALERT_MIN_NET_BUYERS
ALERT_MIN_NET_VALUE_FLOW_USD
ALERT_COOLDOWN_MINUTES
```

## If alerts are too slow

Lower the collector cron interval from 15 minutes to 5 minutes after confirming API costs/rate limits.

## Emergency stop

Disable collector and daily-refresh cron jobs in the hosting provider.

The customer dashboard will remain online but data will stop updating.

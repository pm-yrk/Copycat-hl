# Copycat Render autofill

Run `scripts/copycat_render_autofill.ps1` from PowerShell after creating a Render API key.

The script finds services by name and sets the Copycat environment variables safely. It updates existing services only. If a service is missing, create that worker/cron service in Render and rerun the script.

Required services the script can configure:

- hwt-api
- hwt-frontend
- hwt-live-events
- hwt-collector-live-10s
- hwt-daily-refresh-midnight
- hwt-owned-wallet-scanner
- hwt-backtest-weekly
- hwt-market-universe
- hwt-historical-fill-backfill
- hwt-copycat-platform-migrate
- hwt-telegram-alerts-15m

Do not paste Render API keys or database URLs into ChatGPT.
Do not change COPYCAT_API_KEY_SALT after issuing customer API keys.

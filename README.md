# Copycat collector 10-second worker patch

This patch changes the Render collector from a 15-minute cron job into an always-on background worker named `hwt-collector-live-10s`.

Files changed:
- `render.yaml`
- `infra/render.yaml`
- `backend/app/jobs/collect_loop_local.py`
- `backend/app/settings.py`

After pushing this patch, run a Blueprint/manual sync in Render. If Render asks for environment variables for the new worker, copy the same `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` values from the old collector service.

Once `hwt-collector-live-10s` is running, suspend or delete the old `hwt-collector-15m` cron job if it still appears, so the app does not collect twice.

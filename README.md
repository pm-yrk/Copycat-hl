# Copycat database connection pool fix

This patch changes the backend SQLAlchemy engine to use `NullPool`, so every short API/collector/cron database transaction closes its database connection immediately.

Why: Render runs the API, live collector, and cron jobs as separate containers. With SQLAlchemy's default QueuePool, each container can hold open several Supabase pooler connections. Supabase then rejects new connections with `EMAXCONNSESSION max clients reached in session mode`.

After applying this patch, redeploy all services that use the backend code:

- hwt-api
- hwt-collector-live-10s
- hwt-daily-refresh-midnight

If any old deploy is still running, restart/redeploy it so old pooled connections are dropped.

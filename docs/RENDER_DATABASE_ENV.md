# Render database environment setup

Every backend service that imports `backend/app/db.py` must have a Postgres connection string.

Required on these services:

- `hwt-api`
- `hwt-collector-live-10s`
- `hwt-live-events`
- `hwt-daily-refresh-midnight`
- `hwt-backtest-weekly`

Use one of these environment variable names:

- `DATABASE_URL` preferred
- `SUPABASE_DB_URL`
- `POSTGRES_URL`
- `POSTGRES_PRISMA_URL`
- `POSTGRES_URL_NON_POOLING`

For Supabase, use the project Postgres connection string or Supabase pooler string. Do not paste secrets into logs or screenshots.

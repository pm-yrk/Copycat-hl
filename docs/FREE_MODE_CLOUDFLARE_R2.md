# Copycat free-mode long-term architecture

Goal: keep the pre-launch product at £0/month for as long as possible.

## Architecture

- Cloudflare Pages: frontend/static assets and customer pages.
- Render: FastAPI backend only.
- Supabase Free: auth + current hot dashboard/API data only.
- Cloudflare R2: optional cold archive for compressed historical JSONL files.

## Cloudflare Pages setup

Create a Cloudflare Pages project from the GitHub repo.

Settings:

- Root directory: `frontend`
- Build command: `npm ci && npm run build:cloudflare`
- Output directory: `out`
- Node version: `20`

Environment variables:

```text
CLOUDFLARE_PAGES=1
NEXT_PUBLIC_STATIC_EXPORT=true
NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com
NEXT_PUBLIC_DASHBOARD_FEED_POLL_MS=60000
NEXT_PUBLIC_DASHBOARD_TICK_POLL_MS=15000
NEXT_PUBLIC_PERFORMANCE_POLL_MS=300000
NEXT_PUBLIC_SUPABASE_URL=<your Supabase URL>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your Supabase anon key>
```

After it works, put your custom domain on Cloudflare Pages and set Render `PUBLIC_SITE_URL` to the Cloudflare/custom domain.

## Render free-mode env

`hwt-api`:

```text
COPYCAT_FREE_MODE=true
COPYCAT_DASHBOARD_FEED_CACHE_SECONDS=45
COPYCAT_DASHBOARD_TICK_CACHE_SECONDS=12
COPYCAT_PUBLIC_API_CACHE_SECONDS=300
COPYCAT_DASHBOARD_SIGNAL_LIMIT=60
COPYCAT_DASHBOARD_FLOW_LIMIT=60
COPYCAT_DASHBOARD_ORDER_LIMIT=40
```

`hwt-collector-live-10s`:

```text
COPYCAT_STORE_RAW_JSON=false
COPYCAT_PRUNE_AFTER_COLLECT=true
COPYCAT_POSITIONS_KEEP_SNAPSHOTS=6
COPYCAT_WALLET_SNAPSHOTS_KEEP_PER_WALLET=6
COPYCAT_LIVE_EVENTS_KEEP_DAYS=2
COPYCAT_OWNED_FILLS_KEEP_DAYS=0
```

Pause until R2/cold archive is configured:

```text
hwt-historical-fill-backfill
hwt-market-universe
```

## Optional R2 cold archive

Create a Cloudflare R2 bucket, then add these Render env vars to the worker/API service that will run archive jobs:

```text
COPYCAT_COLD_ARCHIVE_ENABLED=true
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<secret>
R2_SECRET_ACCESS_KEY=<secret>
R2_BUCKET_NAME=copycat-archive
R2_REGION=auto
R2_ARCHIVE_PREFIX=copycat-archive
COPYCAT_COLD_ARCHIVE_BATCH_ROWS=2000
```

Run occasionally:

```text
python -m app.jobs.cold_archive
```

Keep cold archive disabled until the frontend/backend is stable and Supabase is under the free limits.

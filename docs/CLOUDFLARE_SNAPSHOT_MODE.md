# Copycat Cloudflare Snapshot Mode

Snapshot Mode lets the Cloudflare Pages site render dashboard/API preview data from static JSON rather than live Supabase queries.

## Today mode

The patch ships seed files under `frontend/public/copycat-data`. With `NEXT_PUBLIC_STATIC_EXPORT=true`, the frontend reads these first, so the site works even while Supabase egress is blocked.

This is a beta continuity mode: seed data can be stale. It avoids Supabase egress.

## R2 live-ish mode

Create an R2 bucket named `copycat-snapshots`, make it public, add CORS for your Pages domain, then upload the JSON files:

```cmd
set COPYCAT_R2_BUCKET=copycat-snapshots
scripts\copycat_snapshot_publish_once.cmd
```

Then set Cloudflare Pages:

```text
NEXT_PUBLIC_SNAPSHOT_BASE_URL=https://<your-public-r2-url>
NEXT_PUBLIC_SNAPSHOT_FIRST=true
```

For live-ish publishing, run `scripts\copycat_snapshot_from_api_once.cmd` once the Render API can read live data again, then upload with `copycat_snapshot_publish_once.cmd`. A future local Hyperliquid publisher can write these same files without Supabase.

## Files expected by the frontend

- `dashboard-feed.json`
- `dashboard-tick.json`
- `performance-index.json`
- `token-icons.json`
- `api/status.json`
- `api/leaderboard-preview.json`
- `api/token-screener-preview.json`
- `api/coverage-preview.json`
- `api/platform-health.json`

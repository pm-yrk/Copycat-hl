# Snapshot mode troubleshooting

The Cloudflare Pages frontend now tries snapshot JSON in this order for dashboard/API preview paths:

1. `NEXT_PUBLIC_SNAPSHOT_BASE_URL`, for example the public R2 URL.
2. Same-origin bundled files under `/copycat-data`.
3. Live Render API fallback.

This means the dashboard should show bundled snapshot data even if R2 CORS/env is wrong or Supabase is blocked.

After changing Cloudflare Pages environment variables, redeploy the Pages project and hard-refresh the browser.

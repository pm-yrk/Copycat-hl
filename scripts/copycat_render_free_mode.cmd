@echo off
REM Copycat free-mode notes. This script does not need your secrets.
echo.
echo Set these Render environment variables manually on hwt-api and workers:
echo.
echo hwt-api:
echo   COPYCAT_FREE_MODE=true
echo   COPYCAT_DASHBOARD_FEED_CACHE_SECONDS=45
echo   COPYCAT_DASHBOARD_TICK_CACHE_SECONDS=12
echo   COPYCAT_PUBLIC_API_CACHE_SECONDS=300
echo   COPYCAT_DASHBOARD_SIGNAL_LIMIT=60
echo   COPYCAT_DASHBOARD_FLOW_LIMIT=60
echo   COPYCAT_DASHBOARD_ORDER_LIMIT=40
echo.
echo hwt-collector-live-10s:
echo   COPYCAT_STORE_RAW_JSON=false
echo   COPYCAT_PRUNE_AFTER_COLLECT=true
echo   COPYCAT_POSITIONS_KEEP_SNAPSHOTS=6
echo   COPYCAT_WALLET_SNAPSHOTS_KEEP_PER_WALLET=6
echo   COPYCAT_LIVE_EVENTS_KEEP_DAYS=2
echo   COPYCAT_OWNED_FILLS_KEEP_DAYS=0
echo.
echo Pause/disable until R2 is configured:
echo   hwt-historical-fill-backfill
echo   hwt-market-universe
echo.
echo Cloudflare Pages frontend env:
echo   CLOUDFLARE_PAGES=1
echo   NEXT_PUBLIC_STATIC_EXPORT=true
echo   NEXT_PUBLIC_API_BASE_URL=https://hwt-api.onrender.com
echo   NEXT_PUBLIC_DASHBOARD_FEED_POLL_MS=60000
echo   NEXT_PUBLIC_DASHBOARD_TICK_POLL_MS=15000
echo   NEXT_PUBLIC_PERFORMANCE_POLL_MS=300000
echo.
pause

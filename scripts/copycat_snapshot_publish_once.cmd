@echo off
setlocal
if "%COPYCAT_R2_BUCKET%"=="" set COPYCAT_R2_BUCKET=copycat-snapshots
set SNAPSHOT_DIR=%~dp0..\frontend\public\copycat-data

echo Uploading bundled Copycat snapshots from %SNAPSHOT_DIR% to R2 bucket %COPYCAT_R2_BUCKET%...
echo If this is your first time, run: npx wrangler login

for %%F in (dashboard-feed.json dashboard-tick.json performance-index.json token-icons.json) do (
  if exist "%SNAPSHOT_DIR%\%%F" npx wrangler r2 object put %COPYCAT_R2_BUCKET%/%%F --file "%SNAPSHOT_DIR%\%%F"
)
for %%F in (status.json leaderboard-preview.json token-screener-preview.json coverage-preview.json platform-health.json) do (
  if exist "%SNAPSHOT_DIR%\api\%%F" npx wrangler r2 object put %COPYCAT_R2_BUCKET%/api/%%F --file "%SNAPSHOT_DIR%\api\%%F"
)

echo Done. Now set NEXT_PUBLIC_SNAPSHOT_BASE_URL to your public R2 URL when R2 is configured.
endlocal

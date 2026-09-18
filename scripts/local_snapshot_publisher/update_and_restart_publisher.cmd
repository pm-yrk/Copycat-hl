@echo off
setlocal
cd /d "%~dp0\..\.."

where git >nul 2>&1
if errorlevel 1 (
  echo Git is not installed or is not available in this window.
  echo Update the Copycat folder from GitHub, then run start_snapshot_publisher_background.cmd.
  pause
  exit /b 1
)

echo Updating Copycat from GitHub...
git pull --ff-only origin main
if errorlevel 1 (
  echo.
  echo The update stopped safely because this folder has local code changes or cannot reach GitHub.
  echo No files were overwritten.
  pause
  exit /b 1
)

echo Stopping the old publisher...
taskkill /FI "WINDOWTITLE eq Copycat Snapshot Publisher*" /T /F >nul 2>&1
schtasks /end /tn "Copycat Snapshot Publisher" >nul 2>&1
timeout /t 3 /nobreak >nul

cd /d "%~dp0"
set "COPYCAT_NO_PAUSE=1"
call install_windows_startup_task.cmd
call start_snapshot_publisher_background.cmd
echo.
echo Waiting for Cloudflare to confirm publisher version snapshot-v2.3...
powershell -NoProfile -Command "$url='https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev/api/platform-health.json'; for ($i=1; $i -le 40; $i++) { try { $health=Invoke-RestMethod -Uri ($url+'?verify='+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) -TimeoutSec 20; if ($health.publisher_version -eq 'snapshot-v2.3' -and $health.position_history_status -eq 'active') { Write-Host 'Cloudflare confirmed snapshot-v2.3 and active position history.'; exit 0 } } catch {}; Start-Sleep -Seconds 15 }; Write-Host 'The publisher is running, but Cloudflare has not confirmed the new version yet. Check logs\publisher.log.'; exit 1"
echo.
echo Copycat publisher update finished.
pause

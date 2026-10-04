@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
powershell -NoProfile -Command "$running = @(Get-CimInstance Win32_Process ^| Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'publish_snapshots\.py' }); if (-not $running) { exit 0 }; try { $url='https://pub-b9e0279f5eb0496b99c7fa37329e6b53.r2.dev/api/platform-health.json?watchdog='+[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(); $health=Invoke-RestMethod -Uri $url -TimeoutSec 20; $age=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()-[int64]$health.updated_at_ms; if ($age -le 1200000) { exit 7 }; Add-Content -Path 'logs\publisher.log' -Value ('['+(Get-Date)+'] Watchdog found stale Cloudflare data ('+[math]::Round($age/60000)+' minutes); restarting publisher.'); $running ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; exit 0 } catch { exit 7 }"
if "%ERRORLEVEL%"=="7" exit /b 0
echo [%date% %time%] Watchdog found no publisher process; starting it. >> logs\publisher.log
start "Copycat Snapshot Publisher" /min cmd /c ""%~dp0run_snapshot_publisher_loop_silent.cmd""
exit /b 0

@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
powershell -NoProfile -Command "$running = Get-CimInstance Win32_Process ^| Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'publish_snapshots\.py' }; if ($running) { exit 7 }"
if "%ERRORLEVEL%"=="7" exit /b 0
echo [%date% %time%] Watchdog found no publisher process; starting it. >> logs\publisher.log
start "Copycat Snapshot Publisher" /min cmd /c ""%~dp0run_snapshot_publisher_loop_silent.cmd""
exit /b 0

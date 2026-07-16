@echo off
setlocal
set "REPO=C:\dev\hyper_wallet_tracker_saas_v1"
set "ACTIVE=C:\CopycatSnapshotPublisher\local_snapshot_publisher"

cd /d "%REPO%"
if errorlevel 1 exit /b 1

del /q "%ACTIVE%\scanner_state\top50_integrity_changed.flag" >nul 2>&1

py -3 "scripts\wallet_registry\copycat_top50_integrity_v1.py" --repo-root "%REPO%" --active-publisher "%ACTIVE%" --apply
if errorlevel 1 exit /b 1

if not exist "%ACTIVE%\scanner_state\top50_integrity_changed.flag" exit /b 0

powershell -NoProfile -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match '[p]ublish_snapshots\.py' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }"

cd /d "%ACTIVE%"
if exist "run_snapshot_publisher_once.cmd" (
  call "run_snapshot_publisher_once.cmd"
) else (
  py -3 "publish_snapshots.py" --once
)
if errorlevel 1 goto publisher_failed

if exist "start_snapshot_publisher_background.cmd" (
  call "start_snapshot_publisher_background.cmd"
  if errorlevel 1 exit /b 1
)

exit /b 0

:publisher_failed
if exist "start_snapshot_publisher_background.cmd" (
  call "start_snapshot_publisher_background.cmd" >nul 2>&1
)
exit /b 1

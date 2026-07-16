@echo off
setlocal
set "REPO=C:\dev\hyper_wallet_tracker_saas_v1"
set "ACTIVE=C:\CopycatSnapshotPublisher\local_snapshot_publisher"
set "RANK=%REPO%\scripts\wallet_registry\run_consistency_top50_v2.cmd"
set "CHECK=%REPO%\scripts\wallet_registry\copycat_top50_live_integrity_v3.py"

call "%RANK%"
if errorlevel 1 exit /b 1

py -3 "%CHECK%" --repo-root "%REPO%" --active-publisher "%ACTIVE%"
exit /b %ERRORLEVEL%

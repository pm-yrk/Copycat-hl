@echo off
setlocal
schtasks /query /tn "Copycat Snapshot Publisher" /v /fo list
echo.
schtasks /query /tn "Copycat Snapshot Publisher Watchdog" /v /fo list
echo.
echo If both tasks exist, the publisher starts at login and the watchdog checks it every five minutes.
echo.
if exist "C:\CopycatPersistentState\publisher_runtime_status.json" (
  echo Latest publisher runtime status:
  type "C:\CopycatPersistentState\publisher_runtime_status.json"
) else (
  echo No runtime status file exists yet. Start the publisher and check again after its first cycle.
)
pause

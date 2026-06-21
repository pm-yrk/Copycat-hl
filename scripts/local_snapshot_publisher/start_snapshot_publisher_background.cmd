@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
start "Copycat Snapshot Publisher" /min cmd /c "%~dp0run_snapshot_publisher_loop_silent.cmd"
echo Started Copycat snapshot publisher in a minimised window.
echo Check logs\publisher.log for updates.
pause

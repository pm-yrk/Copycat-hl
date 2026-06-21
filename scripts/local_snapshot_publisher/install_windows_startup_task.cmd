@echo off
setlocal
set "TASK_NAME=Copycat Snapshot Publisher"
set "SCRIPT=%~dp0run_snapshot_publisher_loop_silent.cmd"
schtasks /create /tn "%TASK_NAME%" /sc onlogon /tr "\"%SCRIPT%\"" /f
if errorlevel 1 (
  echo Failed to create startup task.
  pause
  exit /b 1
)
echo Installed Windows startup task: %TASK_NAME%
echo It will start the publisher when you log into Windows.
echo To start it now, run start_snapshot_publisher_background.cmd
pause

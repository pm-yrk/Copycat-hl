@echo off
setlocal
set "TASK_NAME=Copycat Snapshot Publisher"
set "WATCHDOG_TASK=Copycat Snapshot Publisher Watchdog"
set "SCRIPT=%~dp0run_snapshot_publisher_loop_silent.cmd"
set "ENSURE_SCRIPT=%~dp0ensure_snapshot_publisher_running.cmd"
schtasks /create /tn "%TASK_NAME%" /sc onlogon /delay 0000:20 /tr "cmd /c \"\"%SCRIPT%\"\"" /f
if errorlevel 1 (
  echo Failed to create startup task.
  if not defined COPYCAT_NO_PAUSE pause
  exit /b 1
)
schtasks /create /tn "%WATCHDOG_TASK%" /sc minute /mo 5 /tr "cmd /c \"\"%ENSURE_SCRIPT%\"\"" /f
if errorlevel 1 (
  echo Startup task was installed, but the five-minute watchdog could not be created.
  if not defined COPYCAT_NO_PAUSE pause
  exit /b 1
)
echo Installed Windows startup task: %TASK_NAME%
echo Installed recovery watchdog: %WATCHDOG_TASK%
echo The publisher starts after login and is restored automatically if it stops.
echo To start it now, run start_snapshot_publisher_background.cmd
if not defined COPYCAT_NO_PAUSE pause

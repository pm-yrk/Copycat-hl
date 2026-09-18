@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
if exist logs\publisher.log for %%F in (logs\publisher.log) do if %%~zF GTR 10485760 move /y logs\publisher.log logs\publisher.previous.log >nul
echo [%date% %time%] Starting Copycat snapshot publisher >> logs\publisher.log
:publisher_loop
py publish_snapshots.py >> logs\publisher.log 2>&1
set "PUBLISHER_EXIT=%ERRORLEVEL%"
if "%PUBLISHER_EXIT%"=="73" (
  echo [%date% %time%] Duplicate publisher detected; watchdog exiting. >> logs\publisher.log
  exit /b 0
)
echo [%date% %time%] Publisher exited with code %PUBLISHER_EXIT%; restarting in 15 seconds. >> logs\publisher.log
timeout /t 15 /nobreak >nul
goto publisher_loop

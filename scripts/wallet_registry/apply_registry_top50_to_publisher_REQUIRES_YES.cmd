@echo off
setlocal
set "REPO=%~dp0..\..\"
set "SOURCE=%REPO%copycat_wallet_registry\exports\recommended_wallets_top50.txt"
set "TARGET=C:\CopycatSnapshotPublisher\local_snapshot_publisher\wallets.txt"
set "BACKUP=C:\CopycatSnapshotPublisher\local_snapshot_publisher\wallets.backup_before_registry_apply.txt"

echo This will replace the LIVE publisher wallet list.
echo Source: %SOURCE%
echo Target: %TARGET%
echo.
echo Scheduled registry tasks DO NOT run this file. This is manual only.
echo Type YES to continue, or close this window.
set /p CONFIRM=Confirm: 
if /I not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 1
)

if not exist "%SOURCE%" (
  echo Missing source file: %SOURCE%
  pause
  exit /b 1
)

copy "%TARGET%" "%BACKUP%" /Y
copy "%SOURCE%" "%TARGET%" /Y

echo.
echo Applied registry top 50 to live publisher.
echo Backup saved to:
echo %BACKUP%
echo.
echo Restart the publisher after changing wallets.
pause

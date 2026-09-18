@echo off
setlocal
schtasks /delete /tn "Copycat Snapshot Publisher" /f
schtasks /delete /tn "Copycat Snapshot Publisher Watchdog" /f
echo Removed startup and watchdog tasks if they existed.
pause

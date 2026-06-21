@echo off
setlocal
schtasks /query /tn "Copycat Snapshot Publisher" /v /fo list
echo.
echo If the task exists, the publisher will start when you log into Windows.
pause

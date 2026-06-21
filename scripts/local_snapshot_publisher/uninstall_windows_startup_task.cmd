@echo off
setlocal
schtasks /delete /tn "Copycat Snapshot Publisher" /f
echo Removed startup task if it existed.
pause

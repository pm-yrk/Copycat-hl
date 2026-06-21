@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
echo [%date% %time%] Starting Copycat snapshot publisher >> logs\publisher.log
py publish_snapshots.py >> logs\publisher.log 2>&1

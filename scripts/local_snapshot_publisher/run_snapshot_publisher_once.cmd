@echo off
setlocal
cd /d "%~dp0"
py publish_snapshots.py --once
pause

@echo off
setlocal
cd /d "%~dp0..\..\"
py "scripts\wallet_registry\copycat_wallet_discovery_v22.py" --repo-root "%CD%" status
pause

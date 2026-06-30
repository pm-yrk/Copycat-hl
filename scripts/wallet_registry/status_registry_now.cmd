@echo off
setlocal
cd /d "%~dp0..\..\"
py "scripts\wallet_registry\copycat_wallet_registry.py" --repo-root "%CD%" status
pause

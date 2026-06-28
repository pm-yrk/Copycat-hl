@echo off
setlocal
cd /d "%~dp0..\..\"
py "scripts\wallet_registry\copycat_wallet_registry.py" --repo-root "%CD%" export --top-n 50
pause

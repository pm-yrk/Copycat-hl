@echo off
setlocal
cd /d "%~dp0..\..\"
echo Discovering wallets and updating local Copycat wallet registry...
py "scripts\wallet_registry\copycat_wallet_registry.py" --repo-root "%CD%" discover
pause

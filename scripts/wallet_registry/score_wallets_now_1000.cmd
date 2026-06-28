@echo off
setlocal
cd /d "%~dp0..\..\"
echo Scoring up to 1000 due wallets using lightweight essential metrics only...
py "scripts\wallet_registry\copycat_wallet_registry.py" --repo-root "%CD%" score --max-scan 1000 --top-n 50 --api-sleep 2.5
pause

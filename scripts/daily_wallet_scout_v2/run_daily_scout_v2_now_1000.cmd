@echo off
setlocal
cd /d "%~dp0..\..\"
echo Starting Copycat Daily Scout v2 now: max 1000 wallets, safe API sleep 2.5s
py "scripts\daily_wallet_scout_v2\copycat_daily_scout_v2.py" --repo-root "%CD%" --max-scan 1000 --top-n 50 --api-sleep 2.5
pause

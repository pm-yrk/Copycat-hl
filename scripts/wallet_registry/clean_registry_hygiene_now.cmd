@echo off
setlocal
cd /d "%~dp0..\..\"
echo Running Copycat Registry Hygiene v2.3
echo This removes obvious non-trader/system/token addresses from the LOCAL registry only.
echo It does NOT change live publisher wallets.
py "scripts\wallet_registry\registry_hygiene_v23.py" --repo-root "%CD%"
pause

@echo off
setlocal
cd /d "%~dp0..\..\"
echo Installing Windows Scheduled Task: Copycat Daily Scout V2
echo Schedule: daily at 06:00 local computer time
echo Mode: recommendations only; does NOT change live publisher wallets automatically
schtasks /Create /TN "Copycat Daily Scout V2" /TR "\"%CD%\scripts\daily_wallet_scout_v2\run_daily_scout_v2_now_500.cmd\"" /SC DAILY /ST 06:00 /F
echo.
echo Done. To confirm:
schtasks /Query /TN "Copycat Daily Scout V2"
pause

@echo off
setlocal
cd /d "%~dp0..\..\"
echo Installing Windows Scheduled Task: Copycat Wallet Registry Scoring
echo Schedule: daily at 06:00 local computer time
echo This scores up to 500 due wallets and exports top-50 recommendation files.
echo It does NOT change live publisher wallets automatically.
schtasks /Create /TN "Copycat Wallet Registry Scoring" /TR "\"%CD%\scripts\wallet_registry\score_wallets_now_500.cmd\"" /SC DAILY /ST 06:00 /F
echo.
schtasks /Query /TN "Copycat Wallet Registry Scoring"
pause

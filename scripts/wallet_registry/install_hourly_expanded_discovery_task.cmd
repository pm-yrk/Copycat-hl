@echo off
setlocal
cd /d "%~dp0..\..\"
echo Installing Windows Scheduled Task: Copycat Expanded Wallet Discovery
echo Schedule: every hour
echo This only discovers wallet addresses. It does not deeply score wallets or change live publisher wallets.
schtasks /Create /TN "Copycat Expanded Wallet Discovery" /TR "\"%CD%\scripts\wallet_registry\discover_expanded_now.cmd\"" /SC HOURLY /MO 1 /F
echo.
schtasks /Query /TN "Copycat Expanded Wallet Discovery"
pause

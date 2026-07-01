@echo off
cd /d "%~dp0"
schtasks /Create /F /TN "CopycatTelegramAlerts" /SC MINUTE /MO 5 /TR "\"%~dp0run_telegram_alerts_once.cmd\""
echo.
echo Copycat Telegram alerts scheduled every 5 minutes.
pause

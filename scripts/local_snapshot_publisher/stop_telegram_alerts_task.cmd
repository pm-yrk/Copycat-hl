@echo off
schtasks /Delete /F /TN "CopycatTelegramAlerts"
echo.
echo Copycat Telegram alerts scheduled task removed.
pause

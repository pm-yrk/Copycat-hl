@echo off
setlocal
cd /d "%~dp0"
if exist "scanner_state\top_wallets.txt" (
  start notepad "scanner_state\top_wallets.txt"
) else (
  echo No top wallets file yet. Run run_local_scanner_update_wallets.cmd first.
  pause
)

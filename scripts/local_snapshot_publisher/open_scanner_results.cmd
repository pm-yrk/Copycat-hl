@echo off
setlocal
cd /d "%~dp0"
if exist "scanner_state\scanner_results.json" (
  start notepad "scanner_state\scanner_results.json"
) else (
  echo No scanner results yet. Run run_local_scanner_once.cmd first.
  pause
)

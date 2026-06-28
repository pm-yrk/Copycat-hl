@echo off
setlocal
cd /d "%~dp0..\..\"
if exist "copycat_wallet_registry\exports" (
  explorer "copycat_wallet_registry\exports"
) else (
  echo No exports folder exists yet.
  pause
)

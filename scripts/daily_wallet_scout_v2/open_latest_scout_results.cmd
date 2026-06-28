@echo off
setlocal
cd /d "%~dp0..\..\"
if exist "copycat_daily_scout_out_v2\latest" (
  explorer "copycat_daily_scout_out_v2\latest"
) else (
  echo No latest scout results folder found yet.
  pause
)

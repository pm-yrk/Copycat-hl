@echo off
setlocal
cd /d "%~dp0..\..\"
echo Previewing Copycat Registry Hygiene v2.3
echo No rows will be deleted in dry-run mode.
py "scripts\wallet_registry\registry_hygiene_v23.py" --repo-root "%CD%" --dry-run
pause

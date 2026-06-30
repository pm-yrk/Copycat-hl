@echo off
setlocal
cd /d "%~dp0..\..\"
echo Running Copycat Wallet Discovery Expansion v2.2
echo This scans imports, Downloads, CopycatArchive, zipped patch files, saved pages, and configured URL sources.
echo It does NOT change live publisher wallets.
py "scripts\wallet_registry\copycat_wallet_discovery_v22.py" --repo-root "%CD%" expand --purge-blocklist
pause

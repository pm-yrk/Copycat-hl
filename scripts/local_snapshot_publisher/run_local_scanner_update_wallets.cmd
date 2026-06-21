@echo off
setlocal
cd /d "%~dp0"
py scan_wallet_candidates.py --update-wallets
pause

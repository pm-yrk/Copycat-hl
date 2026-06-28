@echo off
setlocal
cd /d "%~dp0..\..\"
mkdir "copycat_wallet_registry\imports" 2>nul
explorer "copycat_wallet_registry\imports"

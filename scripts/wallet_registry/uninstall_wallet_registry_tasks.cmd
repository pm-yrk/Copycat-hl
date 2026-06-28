@echo off
schtasks /Delete /TN "Copycat Wallet Discovery" /F
schtasks /Delete /TN "Copycat Wallet Registry Scoring" /F
pause

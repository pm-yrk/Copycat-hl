@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist logs\publisher.log echo No log yet. Run the publisher first.> logs\publisher.log
notepad logs\publisher.log

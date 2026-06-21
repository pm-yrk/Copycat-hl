@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install boto3
if not exist publisher.env copy publisher.env.example publisher.env

echo.
echo Installed Copycat local snapshot publisher dependencies.
echo Next: edit publisher.env and fill your R2 credentials.
echo.
pause

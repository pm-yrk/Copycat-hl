@echo off
setlocal
if "%COPYCAT_API_BASE%"=="" set COPYCAT_API_BASE=https://hwt-api.onrender.com
set SNAPSHOT_DIR=%~dp0..\frontend\public\copycat-data
mkdir "%SNAPSHOT_DIR%\api" 2>nul

echo Pulling latest snapshots from %COPYCAT_API_BASE%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $base=$env:COPYCAT_API_BASE.TrimEnd('/'); $out=$env:SNAPSHOT_DIR; $pairs=@(@('/api/dashboard-feed','dashboard-feed.json'),@('/api/dashboard-tick','dashboard-tick.json'),@('/api/performance-index?max_points=240','performance-index.json'),@('/api/data/v1/status','api/status.json'),@('/api/data/v1/public/leaderboard-preview','api/leaderboard-preview.json'),@('/api/data/v1/public/token-screener-preview','api/token-screener-preview.json'),@('/api/data/v1/public/coverage-preview','api/coverage-preview.json'),@('/api/data/v1/public/platform-health','api/platform-health.json')); foreach($p in $pairs){ try { $url=$base+$p[0]; $dest=Join-Path $out $p[1]; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null; Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 25; Write-Host 'OK' $p[1] } catch { Write-Host 'SKIP' $p[1] $_.Exception.Message } }"

echo Done. Files are in %SNAPSHOT_DIR%.
endlocal

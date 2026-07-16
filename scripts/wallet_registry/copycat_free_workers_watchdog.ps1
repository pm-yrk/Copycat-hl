param()

$repo = "C:\dev\hyper_wallet_tracker_saas_v1"
$discovery = Join-Path $repo "scripts\wallet_registry\copycat_all_market_discovery_v1.py"
$profit = Join-Path $repo "scripts\wallet_registry\copycat_profit_history_worker_v1.py"
$logDir = "C:\CopycatDiagnostics"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Start-WorkerIfMissing {
    param(
        [string]$Needle,
        [string]$ScriptPath,
        [string]$LogName,
        [string[]]$ExtraArgs = @()
    )

    $running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match [regex]::Escape($Needle) }

    if ($running) { return }

    $stdout = Join-Path $logDir "$LogName.log"
    $stderr = Join-Path $logDir "$LogName-error.log"
    $arguments = @(
        "-3",
        "`"$ScriptPath`"",
        "--repo-root",
        "`"$repo`"",
        "--active-publisher",
        "`"C:\CopycatSnapshotPublisher\local_snapshot_publisher`""
    ) + $ExtraArgs

    Start-Process `
        -FilePath "py.exe" `
        -ArgumentList ($arguments -join " ") `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr
}

Start-WorkerIfMissing `
    -Needle "copycat_all_market_discovery_v1.py" `
    -ScriptPath $discovery `
    -LogName "copycat-all-market-discovery"

Start-WorkerIfMissing `
    -Needle "copycat_profit_history_worker_v1.py" `
    -ScriptPath $profit `
    -LogName "copycat-profit-history" `
    -ExtraArgs @("--interval-seconds", "180")

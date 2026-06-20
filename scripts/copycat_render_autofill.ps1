# Copycat Render autofill helper
# This updates environment variables for existing Render services by service name.
# It does NOT print secrets and does NOT change COPYCAT_API_KEY_SALT.

$ErrorActionPreference = "Stop"

function Read-SecretPlain([string]$Prompt) {
  $secure = Read-Host $Prompt -AsSecureString
  $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
function Invoke-RenderApi([string]$Method, [string]$Url, $Body = $null) {
  $headers = @{ Authorization = "Bearer $script:RenderApiKey"; Accept = "application/json" }
  if ($null -ne $Body) {
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8)
  }
  return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers
}
function Service-List() {
  $resp = Invoke-RenderApi "GET" "https://api.render.com/v1/services?limit=100"
  $out = @()
  foreach ($item in @($resp)) {
    if ($item.service) { $out += $item.service }
    elseif ($item.id -and $item.name) { $out += $item }
  }
  return $out
}
function Find-Service([string]$Name) {
  return @($script:Services | Where-Object { $_.name -eq $Name } | Select-Object -First 1)[0]
}
function Set-Env([string]$ServiceName, [hashtable]$Vars) {
  $svc = Find-Service $ServiceName
  if (-not $svc) {
    Write-Host "SKIP missing service: $ServiceName" -ForegroundColor Yellow
    $script:Missing += $ServiceName
    return
  }
  Write-Host "Updating $ServiceName ..." -ForegroundColor Cyan
  foreach ($k in $Vars.Keys) {
    $v = [string]$Vars[$k]
    if ([string]::IsNullOrWhiteSpace($v)) { continue }
    Invoke-RenderApi "PUT" "https://api.render.com/v1/services/$($svc.id)/env-vars/$k" @{ value = $v } | Out-Null
    Write-Host "  set $k"
  }
  $script:Updated += @{ name = $ServiceName; id = $svc.id; type = $svc.type }
}
function Trigger-Deploys() {
  foreach ($u in $script:Updated) {
    try {
      if ($u.type -eq "cron_job") { continue }
      Invoke-RenderApi "POST" "https://api.render.com/v1/services/$($u.id)/deploys" @{ clearCache = "do_not_clear" } | Out-Null
      Write-Host "Triggered deploy: $($u.name)" -ForegroundColor Green
    } catch {
      Write-Host "Could not trigger deploy for $($u.name). Trigger it manually in Render if needed." -ForegroundColor Yellow
    }
  }
}

Write-Host "Copycat Render autofill" -ForegroundColor Green
Write-Host "Create a Render API key in Render Account Settings, then paste it here. Do not paste it into ChatGPT." -ForegroundColor Yellow
$script:RenderApiKey = Read-SecretPlain "Render API key"
$DatabaseUrl = Read-SecretPlain "DATABASE_URL / Supabase Postgres connection string"
$PublicSiteUrl = Read-Host "Public site URL [https://hwt-frontend.onrender.com]"
if ([string]::IsNullOrWhiteSpace($PublicSiteUrl)) { $PublicSiteUrl = "https://hwt-frontend.onrender.com" }
$ApiBaseUrl = Read-Host "API base URL [https://hwt-api.onrender.com]"
if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) { $ApiBaseUrl = "https://hwt-api.onrender.com" }
$TelegramBotToken = Read-SecretPlain "Telegram bot token (optional; press Enter for blank)"
$TelegramChatId = Read-Host "Telegram chat id (optional)"

$script:Services = Service-List
$script:Missing = @()
$script:Updated = @()

Set-Env "hwt-api" @{
  DATABASE_URL = $DatabaseUrl
  PUBLIC_SITE_URL = $PublicSiteUrl
  WALLET_DISCOVERY_PROVIDER = "owned_first"
  COLLECTOR_FRESHNESS_SECONDS = "180"
}
Set-Env "hwt-frontend" @{
  NEXT_PUBLIC_API_BASE_URL = $ApiBaseUrl
}
Set-Env "hwt-live-events" @{
  DATABASE_URL = $DatabaseUrl
  LIVE_EVENT_WALLET_LIMIT = "50"
  LIVE_EVENT_SUBSCRIBE_ORDER_UPDATES = "false"
  LIVE_STATE_WALLET_LIMIT = "50"
  LIVE_STATE_POLL_SECONDS = "5"
  LIVE_STATE_MAX_WORKERS = "10"
  LIVE_STATE_MAX_AGE_SECONDS = "45"
  LIVE_SIGNAL_MIN_COVERAGE_RATIO = "0.8"
}
Set-Env "hwt-collector-live-10s" @{
  DATABASE_URL = $DatabaseUrl
  COLLECTOR_INTERVAL_SECONDS = "1"
  COLLECTOR_MAX_WORKERS = "30"
}
Set-Env "hwt-daily-refresh-midnight" @{
  DATABASE_URL = $DatabaseUrl
  WALLET_DISCOVERY_PROVIDER = "owned"
  OWNED_DISCOVERY_REFRESH_LIMIT = "500"
  OWNED_REFRESH_LIMIT = "75"
  OWNED_REFRESH_MAX_SECONDS = "600"
  OWNED_REFRESH_RUN_COLLECTION = "false"
  OWNED_DISCOVERY_FETCH_FILLS = "false"
}
Set-Env "hwt-owned-wallet-scanner" @{
  DATABASE_URL = $DatabaseUrl
  WALLET_DISCOVERY_PROVIDER = "owned"
  OWNED_SCANNER_BATCH_SIZE = "250"
  OWNED_SCANNER_MAX_SECONDS = "900"
  OWNED_SCANNER_SLEEP_SECONDS = "3600"
  OWNED_TOP_CLAIM_MIN_INDEXED_WALLETS = "10000"
  OWNED_DISCOVERY_FETCH_FILLS = "false"
}
Set-Env "hwt-backtest-weekly" @{
  DATABASE_URL = $DatabaseUrl
}
Set-Env "hwt-market-universe" @{
  DATABASE_URL = $DatabaseUrl
  MARKET_UNIVERSE_SLEEP_SECONDS = "300"
}
Set-Env "hwt-historical-fill-backfill" @{
  DATABASE_URL = $DatabaseUrl
  OWNED_BACKFILL_WALLET_LIMIT = "5"
  OWNED_BACKFILL_DAYS = "365"
  OWNED_BACKFILL_MAX_PAGES_PER_WALLET = "2"
  OWNED_BACKFILL_MAX_SECONDS = "900"
  OWNED_BACKFILL_SLEEP_SECONDS = "3600"
  OWNED_DISCOVERY_FETCH_FILLS = "false"
}
Set-Env "hwt-copycat-platform-migrate" @{
  DATABASE_URL = $DatabaseUrl
}
$telegramVars = @{
  DATABASE_URL = $DatabaseUrl
  TELEGRAM_ALERT_INTERVAL_MINUTES = "15"
}
if (-not [string]::IsNullOrWhiteSpace($TelegramBotToken)) { $telegramVars["TELEGRAM_BOT_TOKEN"] = $TelegramBotToken; $telegramVars["TELEGRAM_ALERT_ENABLED"] = "true" }
if (-not [string]::IsNullOrWhiteSpace($TelegramChatId)) { $telegramVars["TELEGRAM_CHAT_ID"] = $TelegramChatId }
Set-Env "hwt-telegram-alerts-15m" $telegramVars

Trigger-Deploys

Write-Host "Done." -ForegroundColor Green
if ($script:Missing.Count -gt 0) {
  Write-Host "Missing services were not created by this script:" -ForegroundColor Yellow
  $script:Missing | Sort-Object -Unique | ForEach-Object { Write-Host " - $_" }
  Write-Host "Create missing workers/cron jobs in Render, then rerun this script."
}
Write-Host "Remember: do not change COPYCAT_API_KEY_SALT after issuing customer API keys." -ForegroundColor Yellow

#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$DeployDir = if ($env:TELEZON_DEPLOY_DIR) { $env:TELEZON_DEPLOY_DIR } else { $PSScriptRoot }
Set-Location $DeployDir

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example — set TELEGRAM_API_ID / TELEGRAM_API_HASH first."
    } else {
        Write-Error "Missing .env and .env.example in $DeployDir"
    }
}

Write-Host "Pulling images (if needed)..."
docker compose pull app 2>$null
if ($LASTEXITCODE -ne 0) { docker compose pull }

Write-Host "Starting interactive login (phone / code / 2FA)..."
docker compose --profile setup run --rm setup

Write-Host ""
Write-Host "Update .env with SESSION_STRING from above, then:"
Write-Host "  docker compose up -d"

$ErrorActionPreference = 'Stop'

$TargetRoot = 'E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system'
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $TargetRoot "ui_backups\light_enterprise_theme_$Stamp"
$LatestBackupFile = Join-Path $TargetRoot 'LATEST_LIGHT_THEME_BACKUP.txt'

$Files = @(
    'frontend\src\styles.css',
    'frontend\src\components\Layout.tsx'
)

if (!(Test-Path $TargetRoot)) { throw "Target project not found: $TargetRoot" }
if (!(Test-Path (Join-Path $TargetRoot 'docker-compose.yml'))) { throw 'Target docker-compose.yml is missing.' }

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

foreach ($Relative in $Files) {
    $Source = Join-Path $PatchRoot $Relative
    $Destination = Join-Path $TargetRoot $Relative
    $Backup = Join-Path $BackupRoot $Relative

    if (!(Test-Path $Source)) { throw "Patch file missing: $Source" }
    if (!(Test-Path $Destination)) { throw "Target file missing: $Destination" }

    New-Item -ItemType Directory -Path (Split-Path $Backup) -Force | Out-Null
    Copy-Item $Destination $Backup -Force
    Copy-Item $Source $Destination -Force
    Write-Host "Updated: $Relative" -ForegroundColor Cyan
}

Set-Content -Path $LatestBackupFile -Value $BackupRoot -Encoding UTF8

Write-Host ''
Write-Host 'Building frontend only...' -ForegroundColor Yellow
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') build frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend image build failed.' }

Write-Host 'Recreating frontend only...' -ForegroundColor Yellow
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') up -d --no-deps --force-recreate frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend recreation failed.' }

Write-Host 'Restarting Nginx only...' -ForegroundColor Yellow
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') restart nginx
if ($LASTEXITCODE -ne 0) { throw 'Nginx restart failed.' }

Start-Sleep -Seconds 4
try {
    $Response = Invoke-WebRequest -Uri 'http://localhost:3100' -UseBasicParsing -TimeoutSec 15
    Write-Host "Frontend health: HTTP $($Response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host 'Frontend container started, but the browser health check did not respond yet.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'LIGHT ENTERPRISE THEME APPLIED SUCCESSFULLY' -ForegroundColor Green
Write-Host "Target: $TargetRoot" -ForegroundColor Cyan
Write-Host "UI backup: $BackupRoot" -ForegroundColor Yellow
Write-Host 'Backend, database, Redis and MinIO were not recreated.' -ForegroundColor Green

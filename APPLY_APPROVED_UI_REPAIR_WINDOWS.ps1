$ErrorActionPreference = 'Stop'

$target = 'E:\BEST_ASSEST_MANAGEMENT_SYSTEM\asset-management-system'
$sourceRoot = $PSScriptRoot

if (Test-Path (Join-Path $sourceRoot 'patch')) {
    $sourceRoot = Join-Path $sourceRoot 'patch'
}

$files = @(
    'frontend\src\pages\WelcomePage.tsx',
    'frontend\src\pages\LoginPage.tsx',
    'frontend\src\styles.css',
    'frontend\src\components\Layout.tsx',
    'frontend\src\components\Charts.tsx',
    'frontend\src\components\DroneMap.tsx',
    'frontend\public\geospatial-world-grid.svg',
    'frontend\public\welcome-world-map.webp',
    'frontend\public\nakshatech-horizontal-light.png'
)

if (!(Test-Path $target)) {
    throw "Target project folder not found: $target"
}
if (!(Test-Path (Join-Path $target 'docker-compose.yml'))) {
    throw "docker-compose.yml not found in: $target"
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "E:\BEST_ASSEST_MANAGEMENT_SYSTEM\APPROVED_UI_BACKUP_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

Write-Host 'Backing up and applying approved UI files...' -ForegroundColor Cyan
foreach ($relative in $files) {
    $source = Join-Path $sourceRoot $relative
    $destination = Join-Path $target $relative
    $backupFile = Join-Path $backup $relative

    if (!(Test-Path $source)) {
        throw "Patch source file missing: $source"
    }

    if (Test-Path $destination) {
        New-Item -ItemType Directory -Path (Split-Path $backupFile) -Force | Out-Null
        Copy-Item $destination $backupFile -Force
    }

    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item $source $destination -Force
    Write-Host "  Applied: $relative" -ForegroundColor DarkCyan
}

Write-Host ''
Write-Host 'Validating Docker Compose...' -ForegroundColor Cyan
docker compose `
    -p nakshatech_asset_management `
    --project-directory $target `
    -f (Join-Path $target 'docker-compose.yml') `
    config --quiet

Write-Host 'Building only the frontend image...' -ForegroundColor Cyan
docker compose `
    -p nakshatech_asset_management `
    --project-directory $target `
    -f (Join-Path $target 'docker-compose.yml') `
    build frontend

Write-Host 'Recreating only frontend and Nginx...' -ForegroundColor Cyan
docker compose `
    -p nakshatech_asset_management `
    --project-directory $target `
    -f (Join-Path $target 'docker-compose.yml') `
    up -d --no-deps --force-recreate frontend

docker compose `
    -p nakshatech_asset_management `
    --project-directory $target `
    -f (Join-Path $target 'docker-compose.yml') `
    up -d --no-deps --force-recreate nginx

Start-Sleep -Seconds 4

try {
    $response = Invoke-WebRequest -Uri 'http://localhost:3100/' -UseBasicParsing -TimeoutSec 15
    Write-Host "Frontend health check: HTTP $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Warning "Frontend health check did not respond yet: $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'APPROVED UI REPAIR APPLIED SUCCESSFULLY' -ForegroundColor Green
Write-Host "Backup created at: $backup" -ForegroundColor Yellow
Write-Host 'Open http://localhost:3100 and press Ctrl+Shift+R.' -ForegroundColor Cyan
Write-Host 'Backend, database, APIs, roles and business logic were not copied or edited.' -ForegroundColor Green

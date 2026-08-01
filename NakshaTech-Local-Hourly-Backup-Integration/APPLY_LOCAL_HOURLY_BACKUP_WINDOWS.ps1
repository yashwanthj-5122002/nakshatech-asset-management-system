[CmdletBinding()]
param(
    [string]$Target = 'E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$patchRoot = Join-Path $PSScriptRoot 'patch'
if (-not (Test-Path $patchRoot)) {
    throw "Patch folder not found: $patchRoot"
}
if (-not (Test-Path (Join-Path $Target 'backend\app\main.py'))) {
    throw "The target does not look like the NakshaTech project: $Target"
}
if (-not (Test-Path (Join-Path $Target 'docker-compose.yml'))) {
    throw "docker-compose.yml was not found in: $Target"
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = "E:\BEST_ASSEST_MANAGEMENT_SYSTEM\LOCAL_HOURLY_BACKUP_SOURCE_BACKUP_$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$relativeFiles = @(
    '.env.example',
    'docker-compose.yml',
    'backend\app\core\config.py',
    'backend\app\main.py',
    'backend\app\modules\local_backup\__init__.py',
    'backend\app\modules\local_backup\router.py',
    'backend\app\modules\local_backup\service.py',
    'backend\tests\test_end_to_end.py',
    'local-backup-agent\NakshaTechLocalBackupAgent.ps1',
    'local-backup-agent\Install-NakshaTechLocalBackupAgent.ps1',
    'local-backup-agent\Uninstall-NakshaTechLocalBackupAgent.ps1',
    'local-backup-agent\Generate-BackupAgentToken.ps1',
    'INSTALL_LOCAL_BACKUP_AGENT_WINDOWS.cmd',
    'UNINSTALL_LOCAL_BACKUP_AGENT_WINDOWS.cmd',
    'GENERATE_BACKUP_AGENT_TOKEN_WINDOWS.cmd',
    'docs\LOCAL_HOURLY_BACKUP_IMPLEMENTATION.md',
    'docs\LOCAL_BACKUP_DEPLOYMENT_AND_INSTALL.md',
    'docs\LOCAL_BACKUP_MANUAL_TEST.md',
    'FILES_CHANGED_LOCAL_HOURLY_BACKUP.txt'
)

Write-Host "Backing up replaced source files to: $backupRoot" -ForegroundColor Cyan
foreach ($relative in $relativeFiles) {
    $source = Join-Path $Target $relative
    if (Test-Path $source) {
        $destination = Join-Path $backupRoot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

Write-Host 'Applying the backup integration...' -ForegroundColor Cyan
foreach ($relative in $relativeFiles) {
    $source = Join-Path $patchRoot $relative
    if (-not (Test-Path $source)) {
        throw "Patch file is missing: $source"
    }
    $destination = Join-Path $Target $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$localBackupRoot = 'E:\NakshaTech_Backups'
foreach ($folder in @(
    'IT\Current','IT\Monthly','Drone\Current','Drone\Monthly',
    'Management\Current','Management\Monthly','Admin\Current','Admin\Monthly',
    'Crash_Reports','Logs'
)) {
    New-Item -ItemType Directory -Path (Join-Path $localBackupRoot $folder) -Force | Out-Null
}

Push-Location $Target
try {
    Write-Host 'Validating Docker Compose...' -ForegroundColor Cyan
    docker compose config | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'docker compose config failed' }

    Write-Host 'Building and recreating only the backend container...' -ForegroundColor Cyan
    docker compose build backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend Docker build failed' }
    docker compose up -d --no-deps --force-recreate backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend container recreation failed' }

    Start-Sleep -Seconds 8
    $healthy = $false
    foreach ($url in @('http://localhost:8100/api/health', 'http://localhost:8088/api/health')) {
        try {
            $response = Invoke-RestMethod -Uri $url -TimeoutSec 15
            if ($response.status -eq 'healthy') {
                Write-Host "Backend health check passed: $url" -ForegroundColor Green
                $healthy = $true
                break
            }
        }
        catch {}
    }
    if (-not $healthy) {
        Write-Warning 'The source was applied, but the local backend health check did not answer yet. Run docker compose ps and docker compose logs backend.'
    }
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Local hourly backup integration applied.' -ForegroundColor Green
Write-Host 'Frontend files were not changed.'
Write-Host "Source backup: $backupRoot"
Write-Host "Local backup destination prepared: $localBackupRoot"
Write-Host ''
Write-Host 'After the HTTPS subdomain is deployed:' -ForegroundColor Yellow
Write-Host '1. Run GENERATE_BACKUP_AGENT_TOKEN_WINDOWS.cmd.'
Write-Host '2. Configure the three LOCAL_BACKUP/BACKUP_TIMEZONE environment values on the server.'
Write-Host '3. Restart the deployed backend.'
Write-Host '4. Run INSTALL_LOCAL_BACKUP_AGENT_WINDOWS.cmd as Administrator on DESKTOP-SF003TK.'

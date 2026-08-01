$ErrorActionPreference = 'Stop'
$TargetRoot = 'E:\BEST_ASSEST_MANAGEMENT_SYSTEM\BEST_COMPLTEED_FILE\asset-management-system'
$LatestBackupFile = Join-Path $TargetRoot 'LATEST_LIGHT_THEME_BACKUP.txt'
if (!(Test-Path $LatestBackupFile)) { throw 'No recorded Light Theme backup was found.' }
$BackupRoot = (Get-Content $LatestBackupFile -Raw).Trim()
if (!(Test-Path $BackupRoot)) { throw "Backup folder not found: $BackupRoot" }
$Files = @('frontend\src\styles.css','frontend\src\components\Layout.tsx')
foreach ($Relative in $Files) {
  $Source = Join-Path $BackupRoot $Relative
  $Destination = Join-Path $TargetRoot $Relative
  if (!(Test-Path $Source)) { throw "Backup file missing: $Source" }
  Copy-Item $Source $Destination -Force
  Write-Host "Restored: $Relative" -ForegroundColor Cyan
}
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') build frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend rollback build failed.' }
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') up -d --no-deps --force-recreate frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend rollback recreation failed.' }
& docker compose -p nakshatech_asset_management --project-directory $TargetRoot -f (Join-Path $TargetRoot 'docker-compose.yml') restart nginx
Write-Host 'Previous UI restored.' -ForegroundColor Green

@echo off
setlocal
cd /d "%~dp0"
if not exist backups mkdir backups
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set STAMP=%%i
set FILE=backups\asset-management-%STAMP%.sql

echo Creating database backup: %FILE%
docker compose exec -T db pg_dump -U asset_user -d asset_management > "%FILE%"
if errorlevel 1 (
  echo Backup failed. Confirm the database container is running.
  pause
  exit /b 1
)
echo Backup completed successfully.
pause
endlocal

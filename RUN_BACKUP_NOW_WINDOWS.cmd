@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Running NakshaTech scheduled backup now...
docker compose exec -T backend python scripts/run_backup.py --scheduled --created-by "Windows manual backup"
if errorlevel 1 (
  echo.
  echo BACKUP FAILED. Previous successful backups remain unchanged.
  echo Check: docker compose logs backend
  exit /b 1
)

echo.
echo BACKUP COMPLETED.
echo Default external folder: %~dp0..\NAKSHA_BACKUPS
exit /b 0

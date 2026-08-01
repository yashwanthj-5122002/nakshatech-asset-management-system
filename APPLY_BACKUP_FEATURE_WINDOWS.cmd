@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "BACKUP_DIR=%PROJECT_DIR%..\NAKSHA_BACKUPS"

if not exist "docker-compose.yml" (
  echo ERROR: docker-compose.yml was not found in %PROJECT_DIR%
  exit /b 1
)

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if errorlevel 1 (
  echo ERROR: Could not create backup directory: %BACKUP_DIR%
  exit /b 1
)

echo.
echo NakshaTech Backup Feature Installation
echo ======================================
echo Project: %PROJECT_DIR%
echo External backup folder: %BACKUP_DIR%
echo.

echo [1/5] Validating Docker Compose...
docker compose config --quiet
if errorlevel 1 goto :failed

echo [2/5] Building the additive backend and frontend changes...
docker compose up -d --build backend frontend nginx
if errorlevel 1 goto :failed

echo [3/5] Waiting for backend health...
set /a tries=0
:health_loop
set /a tries+=1
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://localhost:8100/api/health; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 goto :healthy
if %tries% GEQ 30 goto :failed
timeout /t 3 /nobreak >nul
goto :health_loop

:healthy
echo [4/5] Creating the first verified complete backup...
docker compose exec -T backend python scripts/run_backup.py --type full --scope all --created-by "Backup feature installation"
if errorlevel 1 (
  echo WARNING: Application started, but the initial backup did not complete.
  echo Check: docker compose logs backend
  goto :verify
)

:verify
echo [5/5] Verifying containers...
docker compose ps

echo.
echo SUCCESS: Backup feature is installed.
echo Backups are stored outside the project at:
echo %BACKUP_DIR%
echo.
echo Open: http://localhost:3100/backups
echo Never run docker compose down -v.
exit /b 0

:failed
echo.
echo ERROR: Installation stopped. Existing database volumes were not deleted.
echo Review: docker compose logs backend frontend nginx
exit /b 1

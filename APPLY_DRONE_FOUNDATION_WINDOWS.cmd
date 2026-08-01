@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo NakshaTech Drone and Survey Module - Foundation Update
echo ============================================================
echo.

echo [1/5] Backing up the existing PostgreSQL database...
if exist BACKUP_DATABASE_WINDOWS.cmd (
  call BACKUP_DATABASE_WINDOWS.cmd
  if errorlevel 1 (
    echo WARNING: The database backup script reported an error.
    echo Review the backup output before continuing.
    pause
    exit /b 1
  )
) else (
  echo ERROR: BACKUP_DATABASE_WINDOWS.cmd was not found.
  pause
  exit /b 1
)

echo.
echo [2/5] Validating Docker Compose configuration...
docker compose config >nul
if errorlevel 1 (
  echo ERROR: docker compose config failed.
  pause
  exit /b 1
)

echo.
echo [3/5] Rebuilding backend and frontend without deleting volumes...
docker compose up -d --build backend frontend nginx
if errorlevel 1 (
  echo ERROR: Docker rebuild failed.
  pause
  exit /b 1
)

echo.
echo [4/5] Waiting for services...
timeout /t 12 /nobreak >nul

echo.
echo [5/5] Checking backend health...
curl.exe -fsS http://localhost:8100/api/health >nul
if errorlevel 1 (
  echo WARNING: Backend health check did not respond on port 8100.
  echo Run: docker compose logs --tail 100 backend
  pause
  exit /b 1
)

echo.
echo SUCCESS: Drone foundation update applied.
echo Existing IT tables and Docker volumes were not deleted or reset.
echo Open: http://localhost:3100/drone
echo Admin import: http://localhost:3100/drone/import
echo.
pause

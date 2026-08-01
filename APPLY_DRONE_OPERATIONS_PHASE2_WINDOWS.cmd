@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo NakshaTech Drone Module - Operational Phase 2
echo Dispatch, Return, Transfer, Assignment and Work Records
echo ============================================================
echo.
echo This update adds separate Drone operational tables and pages.
echo The IT Asset Register, IT Work Records, IT Reports and volumes
echo are not deleted or reset.
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker was not found. Start Docker Desktop and try again.
  pause
  exit /b 1
)

echo [1/6] Backing up the existing PostgreSQL database...
if exist BACKUP_DATABASE_WINDOWS.cmd (
  call BACKUP_DATABASE_WINDOWS.cmd
  if errorlevel 1 (
    echo ERROR: Database backup failed. Resolve it before applying Phase 2.
    pause
    exit /b 1
  )
) else (
  echo ERROR: BACKUP_DATABASE_WINDOWS.cmd was not found.
  pause
  exit /b 1
)

echo.
echo [2/6] Validating Docker Compose configuration...
docker compose config >nul
if errorlevel 1 (
  echo ERROR: docker compose config failed.
  pause
  exit /b 1
)

echo.
echo [3/6] Rebuilding backend and frontend without deleting volumes...
docker compose build backend frontend
if errorlevel 1 (
  echo ERROR: Backend or frontend build failed.
  pause
  exit /b 1
)

echo.
echo [4/6] Recreating backend, frontend and nginx only...
docker compose up -d --force-recreate backend frontend nginx
if errorlevel 1 (
  echo ERROR: Service restart failed.
  pause
  exit /b 1
)

echo.
echo [5/6] Waiting for additive Drone tables and services...
timeout /t 12 /nobreak >nul
curl.exe -fsS http://localhost:8100/api/health >nul
if errorlevel 1 (
  echo ERROR: Backend health check failed.
  echo Run: docker compose logs --tail 150 backend
  pause
  exit /b 1
)

echo.
echo [6/6] Checking the frontend...
curl.exe -fsS http://localhost:3100 >nul
if errorlevel 1 (
  echo ERROR: Frontend did not answer on port 3100.
  echo Run: docker compose logs --tail 150 frontend nginx
  pause
  exit /b 1
)

echo.
echo SUCCESS: Drone Operational Phase 2 applied.
echo Existing IT data and Docker volumes were preserved.
echo.
echo Open Drone Operations: http://localhost:3100/drone/operations
echo Open Drone Work Records: http://localhost:3100/drone/work-records
echo Open Movement History: http://localhost:3100/drone/movements
start "" http://localhost:3100/drone/operations
echo.
echo Press Ctrl+Shift+R once if the previous menu is cached.
pause
endlocal

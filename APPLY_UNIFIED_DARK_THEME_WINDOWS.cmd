@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ==========================================================
echo  NakshaTech Unified Dark Theme - Frontend Only Update
echo ==========================================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker was not found. Start Docker Desktop and try again.
  pause
  exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker Compose is not available.
  pause
  exit /b 1
)

echo [1/5] Validating Docker Compose configuration...
docker compose config -q
if errorlevel 1 goto :failed

echo [2/5] Building only the frontend image...
docker compose build frontend
if errorlevel 1 goto :failed

echo [3/5] Recreating only the frontend container...
docker compose up -d --no-deps --force-recreate frontend
if errorlevel 1 goto :failed

echo [4/5] Restarting Nginx without changing backend or database services...
docker compose restart nginx
if errorlevel 1 goto :failed

echo [5/5] Checking the frontend...
timeout /t 8 /nobreak >nul
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:3100' -TimeoutSec 20; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
  echo WARNING: The frontend health check did not respond yet.
  echo Run: docker compose logs --tail 100 frontend
  echo The backend and database were not recreated by this script.
  pause
  exit /b 1
)

echo.
echo SUCCESS: The unified dark theme is active.
echo Open: http://localhost:3100
echo Press Ctrl+Shift+R once in the browser.
echo.
echo Backend, database, API routes and Docker volumes were not changed.
pause
exit /b 0

:failed
echo.
echo ERROR: The frontend update did not complete.
echo Review: docker compose logs --tail 100 frontend
echo No database volume deletion command was executed.
pause
exit /b 1

@echo off
setlocal
cd /d "%~dp0"

echo.
echo ================================================================
echo NakshaTech Responsive Welcome Page Update
echo ================================================================
echo This rebuilds only the frontend and nginx containers.
echo Existing PostgreSQL data and Docker volumes will be preserved.
echo Do NOT run docker compose down -v.
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker was not found. Start Docker Desktop first.
  pause
  exit /b 1
)

if not exist .env copy .env.example .env >nul

docker compose build --no-cache frontend
if errorlevel 1 (
  echo.
  echo ERROR: Frontend build failed. Review the Docker output above.
  pause
  exit /b 1
)

docker compose up -d --force-recreate frontend nginx
if errorlevel 1 (
  echo.
  echo ERROR: Frontend startup failed. Run: docker compose logs frontend
  pause
  exit /b 1
)

echo.
echo Waiting for the frontend to start...
timeout /t 12 /nobreak >nul

docker compose ps frontend nginx

echo.
echo Welcome page update applied successfully.
echo Open: http://localhost:3100
echo Press Ctrl+Shift+R once if Chrome shows the previous design.
start "" http://localhost:3100
pause
endlocal

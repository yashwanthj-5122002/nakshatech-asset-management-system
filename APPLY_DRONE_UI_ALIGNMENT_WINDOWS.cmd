@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo NakshaTech Drone Module - UI Alignment Update
echo ============================================================
echo.

echo This update changes only Drone frontend presentation files.
echo IT APIs, IT database tables, IT reports and Docker volumes are not reset.
echo.

where docker >nul 2>nul
if errorlevel 1 (
  echo ERROR: Docker was not found. Start Docker Desktop and try again.
  pause
  exit /b 1
)

echo [1/4] Validating Docker Compose configuration...
docker compose config >nul
if errorlevel 1 (
  echo ERROR: docker compose config failed.
  pause
  exit /b 1
)

echo.
echo [2/4] Rebuilding only the frontend image...
docker compose build --no-cache frontend
if errorlevel 1 (
  echo ERROR: Frontend build failed. Review the Docker output above.
  pause
  exit /b 1
)

echo.
echo [3/4] Restarting frontend and nginx only...
docker compose up -d --force-recreate frontend nginx
if errorlevel 1 (
  echo ERROR: Frontend or nginx restart failed.
  pause
  exit /b 1
)

echo.
echo [4/4] Waiting for the frontend...
timeout /t 8 /nobreak >nul
curl.exe -fsS http://localhost:3100 >nul
if errorlevel 1 (
  echo WARNING: The frontend did not answer yet on port 3100.
  echo Run: docker compose logs --tail 100 frontend
  pause
  exit /b 1
)

echo.
echo SUCCESS: Drone UI alignment update applied.
echo Open: http://localhost:3100/drone/assets
start "" http://localhost:3100/drone/assets
echo.
echo If the previous layout remains visible, press Ctrl+Shift+R once.
pause
endlocal

@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker was not found. Install and start Docker Desktop first.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
echo.
echo Rebuilding the NakshaTech frontend with the corrected UI...
docker compose stop frontend nginx
docker compose build --no-cache frontend
if errorlevel 1 (
  echo Frontend build failed. Review the Docker output above.
  pause
  exit /b 1
)
docker compose up -d --force-recreate frontend nginx
echo.
echo UI rebuild complete.
echo Open: http://localhost:3100
echo If an old page remains visible, press Ctrl+F5 in Chrome.
start "" http://localhost:3100
pause
endlocal

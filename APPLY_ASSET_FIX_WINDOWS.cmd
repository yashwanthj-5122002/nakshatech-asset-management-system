@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker was not found. Start Docker Desktop first.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul

echo.
echo Applying the full-page Asset Register and component-history workflow...
echo This command DOES NOT delete the database or Docker volumes.
echo.

docker compose build backend frontend
if errorlevel 1 (
  echo Build failed. Review the output above.
  pause
  exit /b 1
)

docker compose up -d --force-recreate backend frontend nginx
if errorlevel 1 (
  echo Startup failed. Review the output above.
  pause
  exit /b 1
)

echo.
echo Waiting for the services to become ready...
timeout /t 12 /nobreak >nul

docker compose ps
echo.
echo Update complete. Full-page Add Asset and Component History are active.
echo Open: http://localhost:3100
echo Then press Ctrl+Shift+R once in Chrome.
start "" http://localhost:3100
pause
endlocal

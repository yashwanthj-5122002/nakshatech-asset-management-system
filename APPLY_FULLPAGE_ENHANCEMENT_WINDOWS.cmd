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
echo Applying the full-page Asset Form and Component History enhancement...
echo Existing PostgreSQL data and Docker volumes will be preserved.
echo DO NOT close this window until the process is complete.
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
echo Waiting for database schema and application services...
timeout /t 15 /nobreak >nul

docker compose ps
echo.
echo Enhancement applied successfully.
echo Open: http://localhost:3100
echo Add Asset page: http://localhost:3100/assets/new
echo Press Ctrl+Shift+R once after the page opens.
start "" http://localhost:3100/assets
pause
endlocal

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
echo Starting NakshaTech Asset Management System...
echo Frontend: http://localhost:3100
echo Unified:  http://localhost:8088
echo Backend:  http://localhost:8100
echo API Docs: http://localhost:8100/docs
echo.
docker compose up --build
if errorlevel 1 (
  echo.
  echo Startup failed. Review the Docker output above.
  pause
)
endlocal

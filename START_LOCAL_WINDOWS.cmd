@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
  echo .env is missing. Run SETUP_AND_START_LOCAL_WINDOWS.cmd first.
  pause
  exit /b 1
)
docker compose up -d --build
if errorlevel 1 (
  echo Startup failed. Review the Docker output above.
  pause
  exit /b 1
)
echo.
echo NakshaTech Asset Management is starting.
echo Frontend: http://localhost:3100
echo Unified:  http://localhost:8088
echo Backend:  http://localhost:8100
echo API Docs: http://localhost:8100/docs
start "" http://localhost:3100
pause
endlocal

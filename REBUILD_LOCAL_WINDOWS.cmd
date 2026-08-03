@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
  echo .env is missing. Run SETUP_AND_START_LOCAL_WINDOWS.cmd first.
  pause
  exit /b 1
)
docker compose up -d --build --force-recreate frontend backend
if errorlevel 1 (
  echo Rebuild failed.
  pause
  exit /b 1
)
echo Rebuild completed. Open http://localhost:3100 and press Ctrl+Shift+R.
pause
endlocal

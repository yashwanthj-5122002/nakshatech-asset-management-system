@echo off
setlocal
cd /d "%~dp0"
set /p EMAIL=Enter the local application email: 
if "%EMAIL%"=="" (
  echo Email is required.
  pause
  exit /b 1
)
docker compose exec backend python scripts/set_user_password.py "%EMAIL%"
if errorlevel 1 (
  echo Password update failed.
  pause
  exit /b 1
)
echo Password updated.
pause
endlocal

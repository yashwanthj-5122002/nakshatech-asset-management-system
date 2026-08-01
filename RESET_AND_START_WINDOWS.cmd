@echo off
setlocal
cd /d "%~dp0"
echo WARNING: This deletes the local Asset Management database and all Docker volumes.
set /p CONFIRM=Type RESET to continue: 
if /I not "%CONFIRM%"=="RESET" (
  echo Reset cancelled.
  pause
  exit /b 0
)
if not exist .env copy .env.example .env >nul
docker compose down -v
docker compose up --build
if errorlevel 1 pause
endlocal

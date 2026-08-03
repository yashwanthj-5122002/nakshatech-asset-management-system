@echo off
setlocal
cd /d "%~dp0"
echo WARNING: This deletes ONLY this package's local PostgreSQL, Redis, MinIO, and node_modules Docker volumes.
echo It does not affect cPanel or files outside this project folder.
set /p CONFIRM=Type RESET to continue: 
if /I not "%CONFIRM%"=="RESET" (
  echo Reset cancelled.
  pause
  exit /b 0
)
docker compose down -v --remove-orphans
if errorlevel 1 (
  echo Reset failed.
  pause
  exit /b 1
)
docker compose up -d --build
if errorlevel 1 (
  echo Fresh startup failed.
  pause
  exit /b 1
)
echo Fresh local database created and seeded.
start "" http://localhost:3100
pause
endlocal

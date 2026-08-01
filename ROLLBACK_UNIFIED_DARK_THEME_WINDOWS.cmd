@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Restoring the original frontend files supplied with this release...
if not exist "rollback\unified-dark-theme-original\frontend\src\styles.css" (
  echo ERROR: Rollback source files are missing.
  pause
  exit /b 1
)

copy /Y "rollback\unified-dark-theme-original\frontend\src\styles.css" "frontend\src\styles.css" >nul
copy /Y "rollback\unified-dark-theme-original\frontend\src\components\Layout.tsx" "frontend\src\components\Layout.tsx" >nul
copy /Y "rollback\unified-dark-theme-original\frontend\src\components\Charts.tsx" "frontend\src\components\Charts.tsx" >nul
copy /Y "rollback\unified-dark-theme-original\frontend\src\components\DroneMap.tsx" "frontend\src\components\DroneMap.tsx" >nul
if exist "frontend\public\geospatial-world-grid.svg" del /Q "frontend\public\geospatial-world-grid.svg"

docker compose build frontend
if errorlevel 1 goto :failed
docker compose up -d --no-deps --force-recreate frontend
if errorlevel 1 goto :failed
docker compose restart nginx

echo.
echo Rollback completed. Press Ctrl+Shift+R in the browser.
pause
exit /b 0

:failed
echo Rollback files were restored, but the frontend container could not be rebuilt.
echo Run: docker compose logs --tail 100 frontend
pause
exit /b 1

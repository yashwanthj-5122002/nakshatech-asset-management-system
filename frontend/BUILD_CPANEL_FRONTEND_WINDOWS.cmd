@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0BUILD_CPANEL_FRONTEND_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Frontend build failed.
  pause
  exit /b 1
)
echo.
echo Frontend build completed successfully.
pause

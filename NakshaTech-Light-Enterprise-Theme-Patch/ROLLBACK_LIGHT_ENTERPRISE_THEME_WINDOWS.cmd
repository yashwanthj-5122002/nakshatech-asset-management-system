@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ROLLBACK_LIGHT_ENTERPRISE_THEME_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Rollback failed. Review the error above.
  pause
  exit /b 1
)
pause

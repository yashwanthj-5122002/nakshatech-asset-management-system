@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY_LIGHT_ENTERPRISE_THEME_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Theme application failed. Review the error above.
  pause
  exit /b 1
)
echo.
echo Open http://localhost:3100 and press Ctrl+Shift+R once.
pause

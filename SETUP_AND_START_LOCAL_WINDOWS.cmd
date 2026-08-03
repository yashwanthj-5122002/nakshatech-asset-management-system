@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-And-Start-Local.ps1"
if errorlevel 1 (
  echo.
  echo Setup or startup failed. Read the message above.
  pause
  exit /b 1
)
pause
endlocal

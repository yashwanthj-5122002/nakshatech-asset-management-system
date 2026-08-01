@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY_LOCAL_HOURLY_BACKUP_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Patch failed. No database volume was deleted. Review the error above.
  pause
  exit /b 1
)
pause

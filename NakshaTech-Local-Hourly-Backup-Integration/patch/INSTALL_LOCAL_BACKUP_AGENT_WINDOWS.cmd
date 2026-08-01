@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-backup-agent\Install-NakshaTechLocalBackupAgent.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Run this file as Administrator and review the message above.
  pause
  exit /b 1
)
pause

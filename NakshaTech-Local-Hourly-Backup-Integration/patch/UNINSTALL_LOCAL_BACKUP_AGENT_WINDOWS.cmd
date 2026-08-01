@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-backup-agent\Uninstall-NakshaTechLocalBackupAgent.ps1"
pause

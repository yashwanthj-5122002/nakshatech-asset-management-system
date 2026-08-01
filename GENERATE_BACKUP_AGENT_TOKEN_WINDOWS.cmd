@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-backup-agent\Generate-BackupAgentToken.ps1"
pause

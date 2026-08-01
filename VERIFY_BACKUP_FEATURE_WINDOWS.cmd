@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo NakshaTech Backup Feature Verification
echo ======================================
docker compose config --quiet || exit /b 1
docker compose ps
powershell -NoProfile -Command "try { $r=Invoke-RestMethod -TimeoutSec 10 http://localhost:8100/api/health; $r | ConvertTo-Json -Compress } catch { Write-Error $_; exit 1 }" || exit /b 1
if exist "%~dp0..\NAKSHA_BACKUPS" (
  echo [OK] External backup folder exists: %~dp0..\NAKSHA_BACKUPS
) else (
  echo [WARN] External backup folder does not exist yet.
)
echo Open http://localhost:3100/backups and verify role permissions.

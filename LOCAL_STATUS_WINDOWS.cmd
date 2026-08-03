@echo off
setlocal
cd /d "%~dp0"
docker compose ps
echo.
echo Backend health:
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://localhost:8100/api/health -TimeoutSec 5).Content } catch { Write-Host $_.Exception.Message }"
echo.
pause
endlocal

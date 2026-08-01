@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker was not found. Start Docker Desktop first.
  pause
  exit /b 1
)

if not exist .env copy .env.example .env >nul

echo.
echo ================================================================
echo NakshaTech Multi-Change and Monthly Reporting Enhancement
echo ================================================================
echo Existing PostgreSQL records and Docker volumes will be preserved.
echo Do NOT run docker compose down -v.
echo.

docker compose build backend frontend
if errorlevel 1 (
  echo Build failed. Review the output above.
  pause
  exit /b 1
)

docker compose up -d --force-recreate backend frontend nginx
if errorlevel 1 (
  echo Startup failed. Review the output above.
  pause
  exit /b 1
)

echo.
echo Waiting for schema upgrade and application health...
timeout /t 20 /nobreak >nul

docker compose ps
powershell -NoProfile -Command "try { $r = Invoke-RestMethod http://localhost:8100/api/health -TimeoutSec 15; Write-Host ('Backend health: ' + $r.status) } catch { Write-Host 'Backend health check failed. Review: docker compose logs backend' -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Enhancement applied successfully.
echo Work Records: http://localhost:3100/work?mode=component
echo Excel and Reports: http://localhost:3100/reports
echo Press Ctrl+Shift+R once after opening the application.
start "" http://localhost:3100/work?mode=component
pause
endlocal

@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY_APPROVED_UI_REPAIR_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo UI repair failed. Read the error above. No database volumes were deleted.
  pause
  exit /b 1
)
pause

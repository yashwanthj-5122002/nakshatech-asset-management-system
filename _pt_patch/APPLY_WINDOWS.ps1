param([string]$ProjectRoot = "E:\nakshatech-erp-shreeyansh1")
$ErrorActionPreference = "Stop"
$Patch = Join-Path $PSScriptRoot "apply_project_tracking_patch.py"
if (!(Test-Path $Patch)) { throw "Patch installer is missing: $Patch" }
if (!(Test-Path $ProjectRoot)) { throw "ERP project folder is missing: $ProjectRoot" }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Patch --root $ProjectRoot --check
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed; no changes applied." }
    & py -3 $Patch --root $ProjectRoot --apply
} else {
    & python $Patch --root $ProjectRoot --check
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed; no changes applied." }
    & python $Patch --root $ProjectRoot --apply
}
if ($LASTEXITCODE -ne 0) { throw "Patch aborted. Check error above." }
Write-Host "PATCH INSTALLED. No database volumes were deleted." -ForegroundColor Green
Write-Host "Next: run RUN_DOCKER_WINDOWS.ps1 after verifying your Compose ports." -ForegroundColor Cyan

# NakshaTech ERP - audited cancellation of Draft/Returned commercial expenses.
# Windows PowerShell 5.1 compatible.  No DB operations.  Dry run by default.
param(
    [string]$ProjectRoot = (Get-Location).Path,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PSScriptRoot 'patch_manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'patch_manifest.json not found next to installer.'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$allowed = @(
    'backend/app/modules/commercial/service.py',
    'backend/app/modules/commercial/router.py',
    'backend/app/modules/commercial/schemas.py'
)
if (@($manifest.modifications).Count -ne 7) { throw 'Unexpected patch manifest length.' }
$updates = @{}
foreach ($item in $manifest.modifications) {
    $rel = [string]$item.file
    if ($allowed -notcontains $rel) { throw "Unexpected target file: $rel" }
    $target = Join-Path $ProjectRoot ($rel.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Missing source file: $target"
    }
    if (-not $updates.ContainsKey($target)) {
        $raw = [System.IO.File]::ReadAllText($target)
        $bytes = [System.IO.File]::ReadAllBytes($target)
        $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191)
        $updates[$target] = @{
            Original = $raw
            Text = $raw.Replace("`r`n", "`n")
            CRLF = $raw.Contains("`r`n")
            BOM = $bom
        }
    }
    $old = ([string]$item.old).Replace("`r`n", "`n")
    $new = ([string]$item.new).Replace("`r`n", "`n")
    $entry = $updates[$target]
    $matches = [regex]::Matches($entry.Text, [regex]::Escape($old)).Count
    if ($matches -ne 1) {
        throw "Expected one anchor in $rel; found $matches. No files changed."
    }
    $entry.Text = $entry.Text.Replace($old, $new)
}
Write-Host 'PATCH VALIDATION PASSED (3 target files, 7 exact edits)' -ForegroundColor Green
if (-not $Apply) {
    Write-Host 'DRY RUN ONLY: No files or database records changed.' -ForegroundColor Yellow
    exit 0
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backups = @{}
try {
    foreach ($target in ($updates.Keys | Sort-Object)) {
        $backup = "$target.before_bd_expense_fix_$stamp.bak"
        Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
        $backups[$target] = $backup
    }
    foreach ($target in ($updates.Keys | Sort-Object)) {
        $entry = $updates[$target]
        $text = $entry.Text
        if ($entry.CRLF) { $text = $text.Replace("`n", "`r`n") }
        $utf8 = New-Object System.Text.UTF8Encoding -ArgumentList ([bool]$entry.BOM)
        [System.IO.File]::WriteAllText($target, $text, $utf8)
        Write-Host "Updated: $target"
    }
} catch {
    foreach ($target in $backups.Keys) {
        Copy-Item -LiteralPath $backups[$target] -Destination $target -Force
    }
    throw
}
Write-Host 'PATCH APPLIED. Backup files:' -ForegroundColor Green
foreach ($backup in $backups.Values) { Write-Host $backup }
Write-Host 'No project expense was cancelled. Deployment and authenticated cancellation are separate.' -ForegroundColor Yellow

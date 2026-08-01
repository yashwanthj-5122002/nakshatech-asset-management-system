[CmdletBinding()]
param(
    [switch]$RemoveConfiguration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this uninstaller as Administrator.'
}

schtasks.exe /Delete /TN 'NakshaTech Local Backup Health' /F 2>$null | Out-Null
schtasks.exe /Delete /TN 'NakshaTech Local Backup Hourly' /F 2>$null | Out-Null

$shortcutPath = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'NakshaTech Backups.lnk'
if (Test-Path $shortcutPath) { Remove-Item -LiteralPath $shortcutPath -Force }

if ($RemoveConfiguration) {
    $agentDirectory = Join-Path $env:ProgramData 'NakshaTech\LocalBackupAgent'
    if (Test-Path $agentDirectory) { Remove-Item -LiteralPath $agentDirectory -Recurse -Force }
}

Write-Host 'Scheduled backup tasks were removed.' -ForegroundColor Green
Write-Host 'Existing Excel files in E:\NakshaTech_Backups were not deleted.'

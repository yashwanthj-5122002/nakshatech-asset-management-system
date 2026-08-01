[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer as Administrator.'
}

Write-Host ''
Write-Host 'NakshaTech Local Backup Agent Installer' -ForegroundColor Cyan
Write-Host 'This installs local hourly Excel backups and five-minute crash monitoring.'
Write-Host ''

$applicationUrl = (Read-Host 'Deployed application URL, for example https://assets.nakshatech.com').Trim().TrimEnd('/')
if ($applicationUrl -notmatch '^https://') {
    throw 'The deployed application URL must use HTTPS.'
}
$defaultApi = "$applicationUrl/api"
$apiBaseUrl = (Read-Host "Backup API base URL [$defaultApi]").Trim()
if ([string]::IsNullOrWhiteSpace($apiBaseUrl)) { $apiBaseUrl = $defaultApi }
$apiBaseUrl = $apiBaseUrl.TrimEnd('/')
if ($apiBaseUrl -notmatch '^https://') {
    throw 'The backup API URL must use HTTPS.'
}

$defaultRoot = 'E:\NakshaTech_Backups'
$backupRoot = (Read-Host "Local backup folder [$defaultRoot]").Trim()
if ([string]::IsNullOrWhiteSpace($backupRoot)) { $backupRoot = $defaultRoot }
$driveRoot = [System.IO.Path]::GetPathRoot($backupRoot)
if ([string]::IsNullOrWhiteSpace($driveRoot) -or -not (Test-Path $driveRoot)) {
    throw "The backup drive does not exist: $driveRoot"
}

$secureToken = Read-Host 'Paste the LOCAL_BACKUP_AGENT_TOKEN configured on the deployed server' -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
}
if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 32) {
    throw 'The backup token must contain at least 32 characters.'
}

$sourceDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$agentDirectory = Join-Path $env:ProgramData 'NakshaTech\LocalBackupAgent'
New-Item -ItemType Directory -Path $agentDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
foreach ($folder in @('IT\Current','IT\Monthly','Drone\Current','Drone\Monthly','Management\Current','Management\Monthly','Admin\Current','Admin\Monthly','Crash_Reports','Logs')) {
    New-Item -ItemType Directory -Path (Join-Path $backupRoot $folder) -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $sourceDirectory 'NakshaTechLocalBackupAgent.ps1') -Destination (Join-Path $agentDirectory 'NakshaTechLocalBackupAgent.ps1') -Force

$config = [ordered]@{
    ApplicationUrl = $applicationUrl
    ApiBaseUrl = $apiBaseUrl
    BackupRoot = $backupRoot
    HealthCheckMinutes = 5
    HourlyBackupMinute = 55
    ComputerName = $env:COMPUTERNAME
    InstalledBy = $env:USERNAME
    InstalledAt = (Get-Date).ToString('o')
}
$config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $agentDirectory 'config.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $agentDirectory 'backup-token.txt') -Value $token -Encoding UTF8
$token = $null

# Restrict the configuration/token directory to Administrators and SYSTEM.
icacls.exe $agentDirectory /inheritance:r | Out-Null
icacls.exe $agentDirectory /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null

$scriptPath = Join-Path $agentDirectory 'NakshaTechLocalBackupAgent.ps1'
$healthTask = 'NakshaTech Local Backup Health'
$backupTask = 'NakshaTech Local Backup Hourly'
$healthCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode Health"
$backupCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Mode Backup"

schtasks.exe /Delete /TN $healthTask /F 2>$null | Out-Null
schtasks.exe /Delete /TN $backupTask /F 2>$null | Out-Null
schtasks.exe /Create /TN $healthTask /TR $healthCommand /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks.exe /Create /TN $backupTask /TR $backupCommand /SC HOURLY /MO 1 /ST 00:55 /RU SYSTEM /RL HIGHEST /F | Out-Null

# Public Desktop shortcut points to the real E: drive backup folder.
$desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
$shortcutPath = Join-Path $desktop 'NakshaTech Backups.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $backupRoot
$shortcut.WorkingDirectory = $backupRoot
$shortcut.Description = 'Open NakshaTech automatic local backups'
$shortcut.Save()

Write-Host ''
Write-Host 'Testing the deployed backup endpoint and creating the first backup...' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath -Mode Initial
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The agent was installed, but the initial backup failed. Review: $backupRoot\Logs\backup-agent.log"
}
else {
    Write-Host 'Initial backup completed successfully.' -ForegroundColor Green
}

Write-Host ''
Write-Host "Backup folder: $backupRoot" -ForegroundColor Green
Write-Host "Health task: every 5 minutes"
Write-Host "Excel refresh: every hour at minute 55"
Write-Host "Completed month files: preserved under each role's Monthly folder"
Write-Host "Desktop shortcut: $shortcutPath"
Write-Host ''

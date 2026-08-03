$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function New-HexSecret([int]$Bytes = 32) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return -join ($buffer | ForEach-Object { $_.ToString('x2') })
}

function New-LocalPassword {
    $letters = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $buffer = New-Object byte[] 14
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    $body = -join ($buffer | ForEach-Object { $letters[$_ % $letters.Length] })
    return $body + '@9!'
}

function Read-PlainPassword([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    return [System.Net.NetworkCredential]::new('', $secure).Password
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker was not found. Install and start Docker Desktop first.'
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is installed but not running. Start Docker Desktop and try again.'
}

if (-not (Test-Path '.env')) {
    Write-Host ''
    Write-Host 'First-time local setup' -ForegroundColor Cyan
    $softwareTeamEmail = Read-Host 'Software Team email [software-support@nakshatech.com]'
    if ([string]::IsNullOrWhiteSpace($softwareTeamEmail)) {
        $softwareTeamEmail = 'software-support@nakshatech.com'
    }

    do {
        $softwareTeamPassword = Read-PlainPassword 'Create the LOCAL Software Team password (10+ characters; use letters, numbers, @ ! . _ - only)'
        $confirmPassword = Read-PlainPassword 'Confirm the LOCAL Software Team password'
        if ($softwareTeamPassword -ne $confirmPassword) {
            Write-Host 'Passwords do not match. Try again.' -ForegroundColor Yellow
        } elseif ($softwareTeamPassword.Length -lt 10) {
            Write-Host 'Use at least 10 characters.' -ForegroundColor Yellow
        } elseif ($softwareTeamPassword -notmatch '^[A-Za-z0-9@!._-]+$') {
            Write-Host 'Use only letters, numbers, and these symbols: @ ! . _ -' -ForegroundColor Yellow
        }
    } while ($softwareTeamPassword -ne $confirmPassword -or $softwareTeamPassword.Length -lt 10 -or $softwareTeamPassword -notmatch '^[A-Za-z0-9@!._-]+$')

    $organizationAdminName = Read-Host 'New Admin full name [NakshaTech Administrator]'
    if ([string]::IsNullOrWhiteSpace($organizationAdminName)) { $organizationAdminName = 'NakshaTech Administrator' }
    $organizationAdminEmail = Read-Host 'New Admin email [admin@nakshatech.com]'
    if ([string]::IsNullOrWhiteSpace($organizationAdminEmail)) { $organizationAdminEmail = 'admin@nakshatech.com' }
    do {
        $organizationAdminPassword = Read-PlainPassword 'Create the LOCAL Admin password (10+ characters; use letters, numbers, @ ! . _ - only)'
        $organizationAdminConfirm = Read-PlainPassword 'Confirm the LOCAL Admin password'
        if ($organizationAdminPassword -ne $organizationAdminConfirm) {
            Write-Host 'Passwords do not match. Try again.' -ForegroundColor Yellow
        } elseif ($organizationAdminPassword.Length -lt 10) {
            Write-Host 'Use at least 10 characters.' -ForegroundColor Yellow
        } elseif ($organizationAdminPassword -notmatch '^[A-Za-z0-9@!._-]+$') {
            Write-Host 'Use only letters, numbers, and these symbols: @ ! . _ -' -ForegroundColor Yellow
        }
    } while ($organizationAdminPassword -ne $organizationAdminConfirm -or $organizationAdminPassword.Length -lt 10 -or $organizationAdminPassword -notmatch '^[A-Za-z0-9@!._-]+$')

    $managementPassword = New-LocalPassword
    $itPassword = New-LocalPassword
    $dronePassword = New-LocalPassword
    $dbPassword = New-HexSecret 16
    $jwtSecret = New-HexSecret 48
    $minioPassword = New-HexSecret 16
    $backupToken = New-HexSecret 32

    $envLines = @(
        'POSTGRES_DB=asset_management'
        'POSTGRES_USER=asset_user'
        "POSTGRES_PASSWORD=$dbPassword"
        "JWT_SECRET=$jwtSecret"
        'MINIO_ROOT_USER=minioadmin'
        "MINIO_ROOT_PASSWORD=$minioPassword"
        "LOCAL_BACKUP_AGENT_TOKEN=$backupToken"
        ''
        "SEED_ADMIN_EMAIL=$softwareTeamEmail"
        "SEED_ADMIN_PASSWORD=$softwareTeamPassword"
        "SEED_ORGANIZATION_ADMIN_NAME=$organizationAdminName"
        "SEED_ORGANIZATION_ADMIN_EMAIL=$organizationAdminEmail"
        "SEED_ORGANIZATION_ADMIN_PASSWORD=$organizationAdminPassword"
        'SEED_MANAGEMENT_EMAIL=management@nakshatech.com'
        "SEED_MANAGEMENT_PASSWORD=$managementPassword"
        'SEED_IT_EMAIL=it@nakshatech.com'
        "SEED_IT_PASSWORD=$itPassword"
        'SEED_DRONE_EMAIL=drone@nakshatech.com'
        "SEED_DRONE_PASSWORD=$dronePassword"
    )
    [System.IO.File]::WriteAllLines((Join-Path (Get-Location) '.env'), $envLines, [System.Text.UTF8Encoding]::new($false))

    $credentialLines = @(
        'NAKSHA TECH LOCAL DEVELOPMENT LOGINS'
        '====================================='
        'These credentials are for this local Docker database only.'
        ''
        "Software Team: $softwareTeamEmail / $softwareTeamPassword"
        "Admin:         $organizationAdminEmail / $organizationAdminPassword"
        "Management: management@nakshatech.com / $managementPassword"
        "IT:         it@nakshatech.com / $itPassword"
        "Drone:      drone@nakshatech.com / $dronePassword"
        ''
        'Do not upload this file or the .env file to GitHub or cPanel.'
    )
    [System.IO.File]::WriteAllLines((Join-Path (Get-Location) 'LOCAL_LOGIN_CREDENTIALS.txt'), $credentialLines, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Local environment and credentials created.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Building and starting the complete local Docker project...' -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Compose startup failed. Review the output above.'
}

$healthy = $false
for ($attempt = 1; $attempt -le 36; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing 'http://localhost:8100/api/health' -TimeoutSec 4
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 5
    }
}

Write-Host ''
docker compose ps
Write-Host ''
if ($healthy) {
    Write-Host 'Local system is ready.' -ForegroundColor Green
} else {
    Write-Host 'Containers started, but backend health is still warming up. Run LOCAL_STATUS_WINDOWS.cmd after one minute.' -ForegroundColor Yellow
}
Write-Host 'Frontend:      http://localhost:3100'
Write-Host 'Unified app:   http://localhost:8088'
Write-Host 'Backend API:   http://localhost:8100'
Write-Host 'API docs:      http://localhost:8100/docs'
Write-Host 'MinIO console: http://localhost:9005'
Write-Host 'Local logins:  LOCAL_LOGIN_CREDENTIALS.txt'
Start-Process 'http://localhost:3100'

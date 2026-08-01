[CmdletBinding()]
param(
    [ValidateSet('Health', 'Backup', 'Initial')]
    [string]$Mode = 'Health'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$AgentDirectory = Join-Path $env:ProgramData 'NakshaTech\LocalBackupAgent'
$ConfigPath = Join-Path $AgentDirectory 'config.json'
$TokenPath = Join-Path $AgentDirectory 'backup-token.txt'
$StatePath = Join-Path $AgentDirectory 'state.json'
$LockPath = Join-Path $AgentDirectory 'agent.lock'

if (-not (Test-Path $ConfigPath)) {
    throw "Backup agent config was not found: $ConfigPath"
}
if (-not (Test-Path $TokenPath)) {
    throw "Backup agent token was not found: $TokenPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 32) {
    throw 'The local backup token is missing or shorter than 32 characters.'
}

$BackupRoot = [string]$config.BackupRoot
$ApplicationUrl = ([string]$config.ApplicationUrl).TrimEnd('/')
$ApiBaseUrl = ([string]$config.ApiBaseUrl).TrimEnd('/')
$Roles = @('it', 'drone', 'management', 'admin')
$RoleDisplay = @{
    it = 'IT'
    drone = 'Drone'
    management = 'Management'
    admin = 'Admin'
}

$LogDirectory = Join-Path $BackupRoot 'Logs'
$LogPath = Join-Path $LogDirectory 'backup-agent.log'
$CrashDirectory = Join-Path $BackupRoot 'Crash_Reports'

function Ensure-Directories {
    New-Item -ItemType Directory -Path $AgentDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $CrashDirectory -Force | Out-Null
    foreach ($role in $Roles) {
        $display = $RoleDisplay[$role]
        New-Item -ItemType Directory -Path (Join-Path $BackupRoot "$display\Current") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $BackupRoot "$display\Monthly") -Force | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $BackupRoot "$display\Monthly\Review") -Force | Out-Null
    }
}

function Rotate-Log {
    if ((Test-Path $LogPath) -and ((Get-Item $LogPath).Length -gt 10MB)) {
        $archive = Join-Path $LogDirectory ("backup-agent-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Move-Item -LiteralPath $LogPath -Destination $archive -Force
    }
}

function Write-AgentLog([string]$Message, [string]$Level = 'INFO') {
    Rotate-Log
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Get-DefaultState {
    [PSCustomObject]@{
        IsOnline = $null
        ActiveIncidentPath = $null
        LastApplicationSuccess = $null
        LastApiSuccess = $null
        LastBackupSuccess = $null
        LastBackupMonth = $null
        LastBackupFiles = @{}
    }
}

function Load-State {
    if (-not (Test-Path $StatePath)) {
        return Get-DefaultState
    }
    try {
        return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
    }
    catch {
        Write-AgentLog "State file could not be read. A new state will be created. $($_.Exception.Message)" 'WARN'
        return Get-DefaultState
    }
}

function Save-State($State) {
    $temporary = "$StatePath.tmp"
    $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatePath -Force
}

function Get-Headers {
    return @{ 'X-Naksha-Backup-Token' = $token }
}

function Test-WebEndpoint([string]$Url, [hashtable]$Headers = @{}) {
    try {
        $response = Invoke-WebRequest -Uri $Url -Headers $Headers -Method Get -UseBasicParsing -TimeoutSec 25
        return [PSCustomObject]@{
            Success = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
            StatusCode = [int]$response.StatusCode
            Message = "HTTP $($response.StatusCode)"
            Content = $response.Content
        }
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        return [PSCustomObject]@{
            Success = $false
            StatusCode = $statusCode
            Message = $_.Exception.Message
            Content = $null
        }
    }
}

function Test-XlsxFile([string]$Path) {
    if (-not (Test-Path $Path)) { throw "Downloaded file is missing: $Path" }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -lt 1000) { throw "Downloaded workbook is unexpectedly small: $($item.Length) bytes" }

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $first = $stream.ReadByte()
        $second = $stream.ReadByte()
        if ($first -ne 0x50 -or $second -ne 0x4B) {
            throw 'Downloaded file is not an XLSX/ZIP file.'
        }
    }
    finally {
        $stream.Dispose()
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        if ($names -notcontains '[Content_Types].xml' -or $names -notcontains 'xl/workbook.xml') {
            throw 'Downloaded workbook is incomplete or corrupt.'
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Archive-Completed-Months([string]$CurrentMonth) {
    foreach ($role in $Roles) {
        $display = $RoleDisplay[$role]
        $currentDirectory = Join-Path $BackupRoot "$display\Current"
        $monthlyDirectory = Join-Path $BackupRoot "$display\Monthly"
        $reviewDirectory = Join-Path $monthlyDirectory 'Review'
        $pattern = "NakshaTech_${display}_Current_*.xlsx"

        Get-ChildItem -LiteralPath $currentDirectory -Filter $pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name -notmatch '(\d{4}-\d{2})\.xlsx$') { return }
            $fileMonth = $Matches[1]
            if ($fileMonth -eq $CurrentMonth) { return }

            $destination = Join-Path $monthlyDirectory "NakshaTech_${display}_Monthly_${fileMonth}.xlsx"
            if (-not (Test-Path $destination)) {
                Move-Item -LiteralPath $_.FullName -Destination $destination
                Write-AgentLog "Finalized $display monthly backup for $fileMonth: $destination"
            }
            else {
                $existingHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
                $currentHash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                if ($existingHash -eq $currentHash) {
                    Remove-Item -LiteralPath $_.FullName -Force
                    Write-AgentLog "Monthly backup already existed and matched for $display $fileMonth."
                }
                else {
                    $review = Join-Path $reviewDirectory ("NakshaTech_{0}_Monthly_{1}_Review_{2}.xlsx" -f $display, $fileMonth, (Get-Date -Format 'yyyyMMdd-HHmmss'))
                    Move-Item -LiteralPath $_.FullName -Destination $review
                    Write-AgentLog "A different frozen monthly file already existed. Preserved the current file for review: $review" 'WARN'
                }
            }

            $manifest = Join-Path $currentDirectory "NakshaTech_${display}_Current_${fileMonth}.manifest.json"
            if (Test-Path $manifest) {
                $manifestDestination = Join-Path $monthlyDirectory "NakshaTech_${display}_Monthly_${fileMonth}.manifest.json"
                if (-not (Test-Path $manifestDestination)) {
                    Move-Item -LiteralPath $manifest -Destination $manifestDestination
                }
                else {
                    Remove-Item -LiteralPath $manifest -Force
                }
            }
        }
    }
}

function Save-WorkbookAtomically(
    [string]$Role,
    [string]$Month,
    [string]$TemporaryPath,
    [string]$ExpectedChecksum,
    [string]$GeneratedAt,
    [string]$RowCounts
) {
    $display = $RoleDisplay[$Role]
    $currentDirectory = Join-Path $BackupRoot "$display\Current"
    $finalPath = Join-Path $currentDirectory "NakshaTech_${display}_Current_${Month}.xlsx"
    $previousPath = "$finalPath.previous"

    Test-XlsxFile $TemporaryPath
    $actualChecksum = (Get-FileHash -LiteralPath $TemporaryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not [string]::IsNullOrWhiteSpace($ExpectedChecksum) -and $actualChecksum -ne $ExpectedChecksum.ToLowerInvariant()) {
        throw "Checksum mismatch for $display backup. Expected $ExpectedChecksum, received $actualChecksum."
    }

    if (Test-Path $previousPath) { Remove-Item -LiteralPath $previousPath -Force }
    try {
        if (Test-Path $finalPath) {
            Move-Item -LiteralPath $finalPath -Destination $previousPath -Force
        }
        Move-Item -LiteralPath $TemporaryPath -Destination $finalPath -Force
        if (Test-Path $previousPath) { Remove-Item -LiteralPath $previousPath -Force }
    }
    catch {
        if ((-not (Test-Path $finalPath)) -and (Test-Path $previousPath)) {
            Move-Item -LiteralPath $previousPath -Destination $finalPath -Force
        }
        throw
    }

    $manifest = [ordered]@{
        role = $Role
        month = $Month
        file = $finalPath
        size_bytes = (Get-Item -LiteralPath $finalPath).Length
        sha256 = $actualChecksum
        generated_at_server = $GeneratedAt
        downloaded_at_local = (Get-Date).ToString('o')
        row_counts = $null
    }
    if (-not [string]::IsNullOrWhiteSpace($RowCounts)) {
        try { $manifest.row_counts = $RowCounts | ConvertFrom-Json } catch { $manifest.row_counts = $RowCounts }
    }
    $manifestPath = Join-Path $currentDirectory "NakshaTech_${display}_Current_${Month}.manifest.json"
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    return $finalPath
}

function Download-RoleBackup([string]$Role, [string]$ExpectedMonth) {
    $display = $RoleDisplay[$Role]
    $currentDirectory = Join-Path $BackupRoot "$display\Current"
    $temporary = Join-Path $currentDirectory (".download-{0}.tmp" -f [guid]::NewGuid().ToString('N'))
    $url = "$ApiBaseUrl/local-backup/export.xlsx?role=$Role"

    try {
        $response = Invoke-WebRequest -Uri $url -Headers (Get-Headers) -Method Get -UseBasicParsing -TimeoutSec 180 -OutFile $temporary -PassThru
        $month = [string]$response.Headers['X-Backup-Month']
        if ([string]::IsNullOrWhiteSpace($month)) { $month = $ExpectedMonth }
        if ($month -ne $ExpectedMonth) {
            throw "Server backup month $month does not match local month $ExpectedMonth."
        }
        $checksum = [string]$response.Headers['X-Content-SHA256']
        $generatedAt = [string]$response.Headers['X-Generated-At']
        $rowCounts = [string]$response.Headers['X-Row-Counts']
        return Save-WorkbookAtomically -Role $Role -Month $month -TemporaryPath $temporary -ExpectedChecksum $checksum -GeneratedAt $generatedAt -RowCounts $rowCounts
    }
    finally {
        if (Test-Path $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Create-CrashIncident($State, $AppResult, $ApiResult) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $incident = Join-Path $CrashDirectory "Incident_$stamp"
    New-Item -ItemType Directory -Path $incident -Force | Out-Null

    foreach ($role in $Roles) {
        $display = $RoleDisplay[$role]
        $sourceDirectory = Join-Path $BackupRoot "$display\Current"
        $destinationDirectory = Join-Path $incident $display
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Get-ChildItem -LiteralPath $sourceDirectory -Filter '*.xlsx' -File -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destinationDirectory -Force
        }
        Get-ChildItem -LiteralPath $sourceDirectory -Filter '*.manifest.json' -File -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destinationDirectory -Force
        }
    }

    $reportPath = Join-Path $incident 'Crash_Report.txt'
    @(
        'NAKSHATECH ASSET MANAGEMENT - LOCAL CRASH REPORT'
        "Incident started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Application URL: $ApplicationUrl"
        "API URL: $ApiBaseUrl"
        "Application status: $($AppResult.Message)"
        "Backup API status: $($ApiResult.Message)"
        "Last successful backup: $($State.LastBackupSuccess)"
        ''
        'The Excel files copied into this incident folder are the latest previously validated local backups.'
        'A new workbook cannot be generated while the backup API/database is unreachable.'
        ''
        'Health checks:'
    ) | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $State.ActiveIncidentPath = $incident
    Write-AgentLog "Created crash incident package: $incident" 'ERROR'
    return $reportPath
}

function Append-IncidentStatus($State, [string]$Message) {
    if ([string]::IsNullOrWhiteSpace([string]$State.ActiveIncidentPath)) { return }
    $reportPath = Join-Path ([string]$State.ActiveIncidentPath) 'Crash_Report.txt'
    if (Test-Path $reportPath) {
        Add-Content -LiteralPath $reportPath -Value ("{0} - {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message) -Encoding UTF8
    }
}

function Invoke-Backup($State, [string]$Reason = 'Scheduled hourly backup') {
    $healthUrl = "$ApiBaseUrl/local-backup/health"
    $apiResult = Test-WebEndpoint -Url $healthUrl -Headers (Get-Headers)
    if (-not $apiResult.Success) {
        throw "Backup API is unavailable: $($apiResult.Message)"
    }

    $health = $apiResult.Content | ConvertFrom-Json
    $month = [string]$health.reporting_month
    if ($month -notmatch '^\d{4}-\d{2}$') {
        throw "Backup API returned an invalid reporting month: $month"
    }

    Archive-Completed-Months -CurrentMonth $month
    $files = @{}
    foreach ($role in $Roles) {
        $files[$role] = Download-RoleBackup -Role $role -ExpectedMonth $month
        Write-AgentLog "$Reason completed for $($RoleDisplay[$role]): $($files[$role])"
    }

    $State.LastBackupSuccess = (Get-Date).ToString('o')
    $State.LastBackupMonth = $month
    $State.LastBackupFiles = $files
    Save-State $State
    Write-AgentLog "$Reason completed successfully for all four roles."
}

function Invoke-HealthCheck($State) {
    $appResult = Test-WebEndpoint -Url $ApplicationUrl
    $apiResult = Test-WebEndpoint -Url "$ApiBaseUrl/local-backup/health" -Headers (Get-Headers)
    $fullyOnline = $appResult.Success -and $apiResult.Success

    if ($appResult.Success) { $State.LastApplicationSuccess = (Get-Date).ToString('o') }
    if ($apiResult.Success) { $State.LastApiSuccess = (Get-Date).ToString('o') }

    if ($fullyOnline) {
        if ($State.IsOnline -eq $false) {
            Append-IncidentStatus $State 'RECOVERED: Application and backup API are reachable again.'
            Write-AgentLog 'Application recovered after a detected outage.'
            $State.ActiveIncidentPath = $null
            try {
                Invoke-Backup $State 'Recovery backup'
            }
            catch {
                Write-AgentLog "Recovery backup failed: $($_.Exception.Message)" 'ERROR'
            }
        }
        $State.IsOnline = $true
        Save-State $State
        Write-AgentLog 'Health check passed.'
        return
    }

    if ($State.IsOnline -ne $false -or [string]::IsNullOrWhiteSpace([string]$State.ActiveIncidentPath)) {
        Create-CrashIncident -State $State -AppResult $appResult -ApiResult $apiResult | Out-Null
        if ($apiResult.Success) {
            try {
                Invoke-Backup $State 'Crash-time API backup'
            }
            catch {
                Write-AgentLog "Crash-time backup failed: $($_.Exception.Message)" 'ERROR'
            }
        }
    }
    Append-IncidentStatus $State "Application=$($appResult.Message); BackupAPI=$($apiResult.Message)"
    $State.IsOnline = $false
    Save-State $State
    Write-AgentLog "Health check failed. Application=$($appResult.Message); BackupAPI=$($apiResult.Message)" 'ERROR'
}

Ensure-Directories
$lockStream = $null
try {
    try {
        $lockStream = [System.IO.File]::Open($LockPath, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    }
    catch {
        # Another scheduled invocation is already running. This is normal at task overlap.
        exit 0
    }

    $state = Load-State
    switch ($Mode) {
        'Health' { Invoke-HealthCheck $state }
        'Backup' { Invoke-Backup $state }
        'Initial' {
            Invoke-Backup $state 'Initial installation backup'
            Invoke-HealthCheck $state
        }
    }
    exit 0
}
catch {
    try { Write-AgentLog "$Mode failed: $($_.Exception.Message)" 'ERROR' } catch {}
    exit 1
}
finally {
    if ($lockStream) { $lockStream.Dispose() }
}

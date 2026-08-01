Set-StrictMode -Version Latest
$bytes = New-Object byte[] 48
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
Write-Host ''
Write-Host 'Generated LOCAL_BACKUP_AGENT_TOKEN:' -ForegroundColor Cyan
Write-Host $token -ForegroundColor Yellow
Write-Host ''
Write-Host 'Configure the same token in the deployed backend and in the Windows agent installer.'

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$Image = 'nakshatech-crm-cpanel-frontend:latest'
$Container = 'nakshatech-crm-cpanel-frontend-export'
$Output = Join-Path $Here 'CPANEL_UPLOAD'
$Zip = Join-Path (Split-Path $Here -Parent) 'NakshaTech-CRM-Frontend-Upload.zip'

Write-Host 'Building the production React frontend...' -ForegroundColor Cyan
docker build -f Dockerfile.cpanel -t $Image .

if (docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch $Container) {
    docker rm -f $Container | Out-Null
}
if (Test-Path $Output) { Remove-Item $Output -Recurse -Force }
New-Item -ItemType Directory -Path $Output -Force | Out-Null

docker create --name $Container $Image | Out-Null
docker cp "${Container}:/output/." $Output
docker rm -f $Container | Out-Null

if (-not (Test-Path (Join-Path $Output 'index.html'))) {
    throw 'Frontend build did not produce index.html.'
}
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Output '*') -DestinationPath $Zip -CompressionLevel Optimal

Write-Host ''
Write-Host 'Frontend production ZIP created:' -ForegroundColor Green
Write-Host $Zip
Write-Host 'Upload and extract its contents directly into /home/nakshatechws/crm.nakshatech.com'

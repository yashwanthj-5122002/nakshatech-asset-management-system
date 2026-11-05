param([string]$ProjectRoot = "E:\nakshatech-erp-shreeyansh1")
$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot
$files = @("-f", "docker-compose.yml")
if (Test-Path "docker-compose.override.yml") {
    $files += @("-f", "docker-compose.override.yml")
}
if (Test-Path "docker-compose.sathwik-ports.yml") {
    $files += @("-f", "docker-compose.sathwik-ports.yml")
} elseif (Test-Path "docker-compose.sathwik.yml") {
    $files += @("-f", "docker-compose.sathwik.yml")
} else {
    throw "No isolated port override found. Create and verify a safe override first; do not clash with the old Docker stack."
}
docker compose -p nakshatech_sathwik @files config --quiet
if ($LASTEXITCODE -ne 0) { throw "Compose validation failed." }
Write-Host "Review published ports before proceeding:" -ForegroundColor Yellow
docker compose -p nakshatech_sathwik @files config --format json | ConvertFrom-Json | ForEach-Object {
    $_.services.PSObject.Properties | ForEach-Object {
        Write-Host $_.Name ((@($_.Value.ports) | ForEach-Object { $_.published }) -join ', ')
    }
}
Write-Host "Starting the existing test stack. No volume deletion." -ForegroundColor Cyan
docker compose -p nakshatech_sathwik @files up -d --build
if ($LASTEXITCODE -ne 0) { throw "Startup failed. Run docker compose logs to inspect the issue." }
docker compose -p nakshatech_sathwik @files ps
Write-Host "Open the published FRONTEND host port; for the previous isolated override, http://localhost:3200/management/project-tracking" -ForegroundColor Green

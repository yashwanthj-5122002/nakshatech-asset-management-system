# Live KPI snapshot for the Sales / Revenue read model consumed by the Finance Command Center.
# Credentials come from the local git-ignored .env - never hardcode passwords in source (see .env.example).
$ErrorActionPreference = "Stop"
$base = "http://localhost:8100/api"

$financePassword = $env:DEV_COMMON_LOGIN_PASSWORD
if (-not $financePassword) {
    throw "DEV_COMMON_LOGIN_PASSWORD is not set. Point it at your local .env value before running this script (see .env.example)."
}

$body = @{ email = "finance@nakshatech.com"; password = $financePassword; role = "finance" } | ConvertTo-Json
$fin = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body $body

function Snap($label) {
    $r = Invoke-RestMethod -Method Get -Uri "$base/finance/sales-revenue" -Headers @{ Authorization = "Bearer $($fin.access_token)" }
    $k = $r.kpi_summary
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    Write-Host ("realized_revenue_inr  = {0}" -f $k.realized_revenue_inr)
    Write-Host ("outstanding_inr       = {0}" -f $k.outstanding_inr)
    Write-Host ("open_sales_inr        = {0}" -f $k.open_sales_inr)
    Write-Host ("received_against_open = {0}" -f $k.received_against_open_sales_inr)
    Write-Host "-- open sales categories --"
    $k.categories.PSObject.Properties | ForEach-Object { Write-Host ("   {0,-40} {1}" -f $_.Name, $_.Value) }
    Write-Host "-- collection --"
    $k.collection.PSObject.Properties | ForEach-Object { Write-Host ("   {0,-40} {1}" -f $_.Name, $_.Value) }
    Write-Host "-- counts --"
    $k.counts.PSObject.Properties | ForEach-Object { Write-Host ("   {0,-40} {1}" -f $_.Name, $_.Value) }
    Write-Host ("reconciled = {0}  (difference {1})" -f $k.reconciled, $k.reconciliation_difference_inr)
    Write-Host ""
    foreach ($p in $r.projects) {
        Write-Host ("   project {0,-6} status={1,-24} closed_rev={2,-10} outstanding={3}" -f $p.project_id, $p.status, $p.closed_revenue_inr, $p.outstanding_inr)
    }
    return $r
}

Snap "LIVE KPI SNAPSHOT" | Out-Null
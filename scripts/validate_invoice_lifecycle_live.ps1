# Live end-to-end validation of the invoice / payment lifecycle status fix.
# Read-only against the running stack except for the invoices it creates for its own probe project.
$ErrorActionPreference = "Stop"
$base = "http://localhost:8100/api"

# Credentials come from the local git-ignored .env - never hardcode passwords in source (see .env.example).
$testPassword = $env:DEV_COMMON_LOGIN_PASSWORD
if (-not $testPassword) {
    throw "DEV_COMMON_LOGIN_PASSWORD is not set. Point it at your local .env value before running this script (see .env.example)."
}

function Show($label, $obj) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    if ($obj -is [string]) { Write-Host $obj } else { $obj | ConvertTo-Json -Depth 8 }
}

function Login($email, $role) {
    $body = @{ email = $email; password = $testPassword; role = $role } | ConvertTo-Json
    return Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType "application/json" -Body $body
}

$fin = Login "finance@nakshatech.com" "finance"
$bd  = Login "bd@nakshatech.com" "bd"
Write-Host "finance token acquired: $([bool]$fin.access_token)" -ForegroundColor Green
Write-Host "bd token acquired: $([bool]$bd.access_token)" -ForegroundColor Green

$finH = @{ Authorization = "Bearer $($fin.access_token)" }
$bdH  = @{ Authorization = "Bearer $($bd.access_token)" }

# --- Baseline revenue before any payment ---
$rev0 = Invoke-RestMethod -Method Get -Uri "$base/finance/sales-revenue" -Headers $finH
Show "BASELINE revenue KPI" @{
    revenue_amount_inr = $rev0.kpi_summary.revenue_amount_inr
    outstanding_inr    = $rev0.kpi_summary.open_sales_total_inr
    kpi_keys           = ($rev0.kpi_summary.PSObject.Properties.Name -join ", ")
}
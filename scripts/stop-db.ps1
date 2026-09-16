# ==============================================================================
# DeepTutor - Local PostgreSQL Database Stopper
# ==============================================================================

$pgData = "C:\Program Files\PostgreSQL\18\data"
$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"

if (-not (Test-Path $pgCtl)) {
    Write-Error "PostgreSQL 18 bin directory not found at: $pgCtl"
    exit 1
}

$status = & $pgCtl -D $pgData status 2>&1
if ($LASTEXITCODE -ne 0 -or ($status -match "no server running")) {
    Write-Host "PostgreSQL is not currently running." -ForegroundColor Yellow
    exit 0
}

Write-Host "Stopping PostgreSQL server gracefully..." -ForegroundColor Cyan
& $pgCtl -D $pgData -m fast stop

if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL stopped cleanly." -ForegroundColor Green
} else {
    Write-Error "Failed to stop PostgreSQL gracefully."
    exit $LASTEXITCODE
}

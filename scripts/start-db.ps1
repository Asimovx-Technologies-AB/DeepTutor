# ==============================================================================
# DeepTutor - Local PostgreSQL Database Launcher
# ==============================================================================

$pgData = "C:\Program Files\PostgreSQL\18\data"
$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
$logFile = "C:\Program Files\PostgreSQL\18\data\server.log"

if (-not (Test-Path $pgCtl)) {
    Write-Error "PostgreSQL 18 bin directory not found at: $pgCtl"
    exit 1
}

# Check if PostgreSQL is already running
$status = & $pgCtl -D $pgData status 2>&1
if ($status -match "server is running") {
    Write-Host "PostgreSQL is already running." -ForegroundColor Green
    exit 0
}

# Clean stale PID file if server died unexpectedly
$pidFile = Join-Path $pgData "postmaster.pid"
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Starting PostgreSQL server..." -ForegroundColor Cyan
& $pgCtl -D $pgData -l $logFile start

# Test connectivity on port 5432
Start-Sleep -Seconds 2
$conn = Test-NetConnection -ComputerName localhost -Port 5432 -WarningAction SilentlyContinue
if ($conn.TcpTestSucceeded) {
    Write-Host "PostgreSQL started successfully on port 5432." -ForegroundColor Green
} else {
    Write-Warning "PostgreSQL started but port 5432 is not yet responding. Check: $logFile"
}

# ==============================================================================
# DeepTutor - Local PostgreSQL Database Launcher
# ==============================================================================

$pgData = "C:\Program Files\PostgreSQL\18\data"
$pgCtl = "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
$logFile = Join-Path $env:TEMP "postgresql-startup.log"

if (-not (Test-Path $pgCtl)) {
    Write-Error "PostgreSQL 18 bin directory not found at: $pgCtl"
    exit 1
}

# Check if PostgreSQL is already running via pg_ctl
$status = & $pgCtl -D $pgData status 2>&1
if ($LASTEXITCODE -eq 0 -or ($status -match "server is running")) {
    Write-Host "PostgreSQL is already running." -ForegroundColor Green
    exit 0
}

# Check if port 5432 is already actively listening
$conn = Test-NetConnection -ComputerName localhost -Port 5432 -WarningAction SilentlyContinue
if ($conn.TcpTestSucceeded) {
    Write-Host "PostgreSQL is already running and listening on port 5432." -ForegroundColor Green
    exit 0
}

# Safely handle postmaster.pid
$pidFile = Join-Path $pgData "postmaster.pid"
if (Test-Path $pidFile) {
    try {
        $firstLine = (Get-Content $pidFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
        if ($firstLine -match '^\d+$') {
            $runningProc = Get-Process -Id [int]$firstLine -ErrorAction SilentlyContinue
            if ($runningProc) {
                Write-Host "PostgreSQL is already running (PID: $firstLine)." -ForegroundColor Green
                exit 0
            }
        }
    } catch {
        # ignore read errors
    }
    Write-Warning "Found stale postmaster.pid (process is not running). Cleaning up..."
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# Clean any legacy server.log inside pgData to prevent Windows sharing violations
$legacyLog = Join-Path $pgData "server.log"
if (Test-Path $legacyLog) {
    Remove-Item $legacyLog -Force -ErrorAction SilentlyContinue
}

Write-Host "Starting PostgreSQL server..." -ForegroundColor Cyan
& $pgCtl -D $pgData -l $logFile -w -t 120 start

if ($LASTEXITCODE -ne 0) {
    Write-Error "PostgreSQL failed to start. Recent log entries:"
    $recentLog = Get-ChildItem (Join-Path $pgData "log") -Filter "*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($recentLog) {
        Get-Content $recentLog.FullName -Tail 20 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    }
    exit $LASTEXITCODE
}

# Test connectivity on port 5432
Start-Sleep -Seconds 1
$conn = Test-NetConnection -ComputerName localhost -Port 5432 -WarningAction SilentlyContinue
if ($conn.TcpTestSucceeded) {
    Write-Host "PostgreSQL started successfully on port 5432." -ForegroundColor Green
} else {
    Write-Warning "PostgreSQL started but port 5432 is not yet responding. Check logs in: $(Join-Path $pgData 'log')"
}


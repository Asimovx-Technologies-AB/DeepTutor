[CmdletBinding()]
param(
    [ValidateSet("azure_openai", "ollama", "gemini")]
    [string]$ChatProvider = "azure_openai",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$envTarget = Join-Path $backendDir ".env"
$envTemplate = Join-Path $backendDir ".env.canonical-local.example"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install and start Docker Desktop for Windows."
}

docker compose --file (Join-Path $repoRoot "compose.yml") up --detach postgres
if ($LASTEXITCODE -ne 0) { throw "Could not start the PostgreSQL container." }

$healthy = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    docker compose --file (Join-Path $repoRoot "compose.yml") exec -T postgres `
        pg_isready -U deeptutor -d deeptutor *> $null
    if ($LASTEXITCODE -eq 0) { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) { throw "PostgreSQL did not become healthy within 60 seconds." }

if (-not (Test-Path $envTarget)) {
    Copy-Item $envTemplate $envTarget
    (Get-Content $envTarget) `
        -replace '^LLM_PROVIDER=.*$', "LLM_PROVIDER=$ChatProvider" |
        Set-Content $envTarget
    Write-Host "Created backend/.env with chat provider '$ChatProvider'."
} else {
    Write-Host "backend/.env already exists; it was preserved."
}

if (-not $SkipDependencies) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python launcher 'py' was not found. Install Python 3.11."
    }
    $venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        & py -3.11 -m venv (Join-Path $backendDir ".venv")
    }
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $venvPython -m pip install -r (Join-Path $backendDir "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install backend dependencies." }

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js 22."
    }
    Push-Location $frontendDir
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "Could not install frontend dependencies." }
    } finally { Pop-Location }
}

Write-Host "Local infrastructure is ready. Run .\scripts\dev-check.ps1 next."

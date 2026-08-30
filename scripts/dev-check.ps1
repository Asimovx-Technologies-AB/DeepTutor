[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "compose.yml"
$envFile = Join-Path $repoRoot "backend\.env"

if (-not (Test-Path $envFile)) {
    throw "backend/.env is missing. Run .\scripts\dev-setup.ps1 first."
}

$required = @{
    "ALLOW_SQLITE_FALLBACK" = "false"
    "VECTOR_STORE_BACKEND" = "pgvector"
}
$values = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}
foreach ($key in $required.Keys) {
    if ($values[$key] -ne $required[$key]) {
        throw "Canonical profile requires $key=$($required[$key])."
    }
}
if ($values["DATABASE_URL"] -notmatch '^postgresql') {
    throw "Canonical profile requires a PostgreSQL DATABASE_URL."
}

docker compose --file $composeFile exec -T postgres `
    psql -U deeptutor -d deeptutor -v ON_ERROR_STOP=1 `
    -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL/pgvector validation failed." }

Write-Host "Canonical database profile is valid."
Write-Host "Chat provider: $($values['LLM_PROVIDER'])"
Write-Host "Embedding provider: $($values['EMBEDDING_PROVIDER'])"
if ($values["EMBEDDING_PROVIDER"] -ne "azure_openai" -or $values["PGVECTOR_DIMENSIONS"] -ne "1536") {
    Write-Warning "This embedding profile differs from deployed Azure development. Re-index documents and run canonical validation before merging."
}

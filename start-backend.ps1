$ErrorActionPreference = 'Stop'
$backendDir = Join-Path $PSScriptRoot 'backend'
$pythonExe = Join-Path $backendDir '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonExe) -or !(Test-Path -LiteralPath (Join-Path $backendDir '.env'))) {
    throw 'Run setup.ps1 first to create the backend environment.'
}
Push-Location $backendDir
try {
    & $pythonExe -m uvicorn app.main:app --reload --reload-include .env --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw 'Backend exited with an error.' }
} finally {
    Pop-Location
}

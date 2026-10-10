$ErrorActionPreference = 'Stop'
$frontendDir = Join-Path $PSScriptRoot 'frontend'
if (!(Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules')) -or !(Test-Path -LiteralPath (Join-Path $frontendDir '.env'))) {
    throw 'Run setup.ps1 first to create the frontend environment.'
}
Push-Location $frontendDir
try {
    & npm.cmd run dev -- --host localhost --port 5173 --strictPort
    if ($LASTEXITCODE -ne 0) { throw 'Frontend exited with an error.' }
} finally {
    Pop-Location
}

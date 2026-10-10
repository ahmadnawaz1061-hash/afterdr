$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer before setup.' }
    & node -e "const [major, minor] = process.versions.node.split('.').map(Number); if (!((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22)) process.exit(1)"
    if ($LASTEXITCODE -ne 0) { throw 'Install Node.js 20.19+ or 22.12+ before setup.' }

    & python -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the Python virtual environment.' }
    & ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

    @'
from pathlib import Path
import secrets
for directory in ('backend', 'frontend'):
    target = Path(directory) / '.env'
    if target.exists():
        print(f'Preserved {target}')
        continue
    template = (Path(directory) / '.env.example').read_text(encoding='utf-8')
    if directory == 'backend':
        template = template.replace(
            'replace-with-a-random-secret-at-least-32-characters',
            secrets.token_urlsafe(48),
        )
    target.write_text(template, encoding='utf-8')
    print(f'Created {target}')
'@ | & ./backend/.venv/Scripts/python.exe -
    if ($LASTEXITCODE -ne 0) { throw 'Environment file setup failed.' }

    Push-Location frontend
    try {
        & npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    } finally {
        Pop-Location
    }
    Write-Host 'Setup complete. Add GEMINI_API_KEY to backend/.env for live image extraction.'
    Write-Host 'Run start-backend.ps1 and start-frontend.ps1 in separate terminals.'
} finally {
    Pop-Location
}

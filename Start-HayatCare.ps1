$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create a Python 3.12 virtual environment and install requirements.txt first. See README.md.'
}
Write-Host 'Starting HayatCare at http://localhost:5000. Keep this process running for reminders and pending fall alerts.'
& $projectPython run.py

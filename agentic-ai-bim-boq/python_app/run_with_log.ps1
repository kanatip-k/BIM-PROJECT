# Migration-safe launcher: provide credentials through the process environment.
# No credential is stored in this script. Uses the project virtual environment.
$ErrorActionPreference = 'Stop'
$env:NAVIS_BRIDGE_URL = 'http://127.0.0.1:8765'
$ProjectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ProjectPython)) {
    throw 'Create python_app/.venv and install requirements.txt first.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ProjectPython -u run_uniformat_takeoff.py *> (Join-Path $PSScriptRoot 'run_output.txt')
    $TaskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $TaskExitCode

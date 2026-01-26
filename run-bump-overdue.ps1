# Runs td bump-overdue with optional local env file.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $scriptDir 'set-td-env.ps1'
if (Test-Path $envFile) {
    . $envFile
}

# Ensure working directory is the repo root
Set-Location $scriptDir

python -m td bump-overdue --apply
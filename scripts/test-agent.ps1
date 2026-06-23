$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$agent = Join-Path $root "apps\agent"

Push-Location $agent
try {
  $env:PYTHONPATH = $agent
  python -m unittest discover -s tests
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

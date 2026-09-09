$ErrorActionPreference = "Stop"
$root = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) { throw "Not inside a Git repository." }
Push-Location $root
try {
    & py -3.13 -X faulthandler -m tools.git_hook pre-push --root $root
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

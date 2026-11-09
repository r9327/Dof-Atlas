<#
.SYNOPSIS
  Prepare the approved Atlas Doctor OSS scanners on Windows.
.DESCRIPTION
  Checks by default. -Install is an explicit developer-only opt-in:
  installs pinned PyPI wheels into the user's Python 3.13 environment.
  Never modifies DOFUS ATLAS runtime dependencies or installs on Doctor startup.
#>
param([switch]$Install)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    $pythonVersion = & py -3.13 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
    if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne "3.13") {
        throw "Python 3.13 is required; install it separately."
    }

    if ($Install) {
        Write-Host "Developer opt-in: installing pinned wheels for Ruff and zizmor."
        & py -3.13 -m pip install --user --only-binary=:all: "ruff==0.17.3" "zizmor==1.30.1"
        if ($LASTEXITCODE -ne 0) {
            throw "Python wheel installation failed; no qualification performed."
        }
    }

    $paths = @(
        "tools/atlas_doctor_lib/oss_router.py",
        ".github/workflows/phase-certification.yml"
    )
    # Python user installations may place zizmor.exe outside PATH. Doctor
    # resolves that trusted user-Scripts path without editing the user's PATH.
    $output = & py -3.13 -X utf8 -m tools.atlas_doctor oss @paths --verify-live --timeout-seconds 45 --json
    $exitCode = $LASTEXITCODE
    if (-not $output) {
        throw "Doctor did not produce qualification JSON (exit $exitCode)."
    }
    $report = ($output -join [Environment]::NewLine) | ConvertFrom-Json
    $report | ConvertTo-Json -Depth 10
    if ($exitCode -ne 0 -or $report.status -ne "LIVE_PASS" -or
        -not $report.windows_13_qualified) {
        throw "Not qualified. Check status/tool_statuses/versions_observed above; missing tools must not be reported as PASS."
    }
    Write-Host "PASS: Ruff and zizmor executed locally on Windows/Python 3.13."
}
finally {
    Pop-Location
}

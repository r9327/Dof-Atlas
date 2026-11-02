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
        # Windows x64-only lock. PyPI wheel checksums verified against the
        # published per-file SHA256 records on 2026-11-02. Other OS/arch tags
        # are intentionally refused, never installed with an unchecked hash.
        $supported = & py -3.13 -c "import platform,sys; print(int(sys.platform == 'win32' and platform.machine().upper() in ('AMD64', 'X86_64') and sys.maxsize > 2**32))"
        if ($LASTEXITCODE -ne 0 -or ($supported -join "").Trim() -ne "1") {
            throw "Hashed Doctor OSS installation supports Windows x64 / Python 3.13 only."
        }
        $lock = [System.IO.Path]::GetTempFileName()
        try {
            $pins = @'
ruff==0.17.3 --hash=sha256:56b8ffb3f3b3cbccb8b76b71b38261b7ed982ef5d20f5b447b1b61a7f4949b24
zizmor==1.30.1 --hash=sha256:06e039fae8e185e2a1a8b002f2d95a6f5c3b548048bdd79e004dcb501fcd0868
'@
            Set-Content -LiteralPath $lock -Value $pins -Encoding ascii
            Write-Host "Developer opt-in: verifying and installing only the two pinned PyPI Windows x64 wheels."
            & py -3.13 -m pip --isolated install --user --only-binary=:all: --no-deps --no-cache-dir --disable-pip-version-check --require-hashes --index-url "https://pypi.org/simple" -r $lock
            if ($LASTEXITCODE -ne 0) {
                throw "Hashed wheel installation failed; do not claim qualification."
            }
        }
        finally {
            Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue
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

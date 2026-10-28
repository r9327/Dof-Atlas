<#
.SYNOPSIS
Optional, manually invoked Windows setup for RTK/Codex.
.DESCRIPTION
May install RTK/ripgrep with winget if missing and configures Codex (globally
by default, or for the current project with -Project). This is not an Atlas
runtime, CI or agent-automation entry point. Run only by explicit choice.
#>

[CmdletBinding()]
param(
    [switch]$Project,
    [switch]$SkipRipgrep
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found on PATH."
    }
    return $command
}

$rtk = Get-Command "rtk" -ErrorAction SilentlyContinue

if (-not $rtk) {
    $winget = Require-Command "winget"
    Write-Host "Installing Rust Token Killer (RTK) with winget..."
    & $winget.Source install --id rtk-ai.rtk -e --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install rtk-ai.rtk (exit $LASTEXITCODE)."
    }
    $rtk = Get-Command "rtk" -ErrorAction SilentlyContinue
}

if (-not $rtk) {
    throw "RTK was installed but is not visible in this PowerShell session. Open a new PowerShell window and rerun this script."
}

if (-not $SkipRipgrep -and -not (Get-Command "rg" -ErrorAction SilentlyContinue)) {
    $winget = Require-Command "winget"
    Write-Host "Installing ripgrep, used by some RTK filters..."
    & $winget.Source install --id BurntSushi.ripgrep.MSVC -e --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install ripgrep (exit $LASTEXITCODE)."
    }
}

Write-Host "Verifying RTK binary..."
& $rtk.Source --version
if ($LASTEXITCODE -ne 0) {
    throw "rtk --version failed."
}

& $rtk.Source gain
if ($LASTEXITCODE -ne 0) {
    throw "rtk gain failed. Another package named 'rtk' may be installed instead of Rust Token Killer."
}

if ($Project) {
    Write-Host "Configuring RTK for Codex in this repository..."
    & $rtk.Source init --codex
} else {
    Write-Host "Configuring RTK globally for Codex..."
    & $rtk.Source init -g --codex
}
if ($LASTEXITCODE -ne 0) {
    throw "RTK Codex initialization failed (exit $LASTEXITCODE)."
}

Write-Host "RTK is installed and configured for Codex. Restart Codex before relying on the hook."

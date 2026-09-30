[CmdletBinding()]
param(
    [string]$Version = "0.9.72",
    [switch]$Open
)
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot
if ($Version -ne "0.9.72") {
    throw "Dofus Atlas requires pinned graphifyy==0.9.72."
}
# Installation is explicit; the Python engine owns the pinned tool configuration.
py -3.13 -m tools.graphify install
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$doctorArgs = @("-3.13", "-m", "tools.atlas_doctor", "graph", "--rebuild")
if ($Open) { $doctorArgs += "--open" }
& py @doctorArgs
exit $LASTEXITCODE

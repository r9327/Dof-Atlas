[CmdletBinding()]
param(
    [string]$Version = "0.9.72",
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    throw "uv is required. Install it once with: winget install astral-sh.uv"
}

$package = "graphifyy==$Version"
Write-Host "Installing Graphify $Version as an isolated uv tool..."
& $uv.Source tool install $package
if ($LASTEXITCODE -ne 0) {
    throw "Graphify installation failed with exit code $LASTEXITCODE"
}

$toolBin = (& $uv.Source tool dir --bin).Trim()
$graphifyExe = Join-Path $toolBin "graphify.exe"
if (-not (Test-Path -LiteralPath $graphifyExe)) {
    $graphifyCmd = Get-Command graphify -ErrorAction SilentlyContinue
    if (-not $graphifyCmd) {
        throw "Graphify was installed but graphify.exe could not be located. Run: uv tool update-shell"
    }
    $graphifyExe = $graphifyCmd.Source
}

Write-Host "Building local AST-only code graph..."
& $graphifyExe extract . --code-only
if ($LASTEXITCODE -ne 0) {
    throw "Graphify extraction failed with exit code $LASTEXITCODE"
}

$graphPath = Join-Path $repoRoot "graphify-out\graph.json"
$htmlPath = Join-Path $repoRoot "graphify-out\graph.html"
if (-not (Test-Path -LiteralPath $graphPath)) {
    throw "Graphify finished without graphify-out\graph.json"
}
if (-not (Test-Path -LiteralPath $htmlPath)) {
    throw "Graphify finished without graphify-out\graph.html"
}

Write-Host "Graphify ready: $graphPath"
Write-Host "Visual map: $htmlPath"
Write-Host "The generated graphify-out directory is intentionally local and ignored by Git."

if ($Open) {
    Start-Process $htmlPath
}

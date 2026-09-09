param([string]$RepoRoot = "")
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (& git rev-parse --show-toplevel).Trim()
}
$resolved = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolved ".git"))) { throw "Not a Git worktree: $resolved" }
if (-not (Test-Path -LiteralPath (Join-Path $resolved ".githooks\pre-commit"))) { throw "Tracked hooks are missing." }
& git -C $resolved config --local core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$configured = (& git -C $resolved config --local --get core.hooksPath).Trim()
if ($configured -ne ".githooks") { throw "Local hooksPath was not configured." }
Write-Host "Dofus Atlas hooks installed locally: $configured"

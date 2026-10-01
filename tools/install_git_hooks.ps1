param([string]$RepoRoot = "")
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (& git rev-parse --show-toplevel).Trim()
}

$resolved = (Resolve-Path -LiteralPath $RepoRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $resolved ".git"))) {
    throw "Not a Git worktree: $resolved"
}

$preCommit = Join-Path $resolved ".githooks\pre-commit"
$prePush = Join-Path $resolved ".githooks\pre-push"
if (-not (Test-Path -LiteralPath $preCommit -PathType Leaf)) {
    throw "Tracked pre-commit hook is missing."
}
if (-not (Test-Path -LiteralPath $prePush -PathType Leaf)) {
    throw "Tracked pre-push hook is missing."
}

& git -C $resolved config --local core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$configured = (& git -C $resolved config --local --get core.hooksPath).Trim()
if ($configured -ne ".githooks") {
    throw "Local hooksPath was not configured."
}

Write-Host "Git hooks path ........ PASS (.githooks)"
Write-Host "pre-commit ............ PASS"
Write-Host "pre-push .............. PASS"

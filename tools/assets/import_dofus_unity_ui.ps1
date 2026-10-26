# Import non destructif des assets Unity identifies dans les planches de l'utilisateur.
# Usage depuis un clone local de r9327/Dof-Atlas (PR #254) :
#   powershell -ExecutionPolicy Bypass -File tools/assets/import_dofus_unity_ui.ps1 -BackgroundPath "chemin\\capture.png"
# Le script ne telecharge rien et ne modifie jamais l'installation du jeu.
[CmdletBinding()]
param(
    [string] $SourceRoot = (Join-Path $env:USERPROFILE 'Documents\Atlas-Dofus-UI-Composants'),
    [string] $BackgroundPath = '',
    [switch] $IncludeDofusLogo
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifest = Join-Path $repo 'docs\plans\guides-2026-10-24\06b-dofus-unity-asset-manifest.csv'
if (!(Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw "Source introuvable: $SourceRoot" }
if (!(Test-Path -LiteralPath $manifest -PathType Leaf)) { throw "Manifeste introuvable: $manifest" }
$target = Join-Path $repo 'app\assets\themes\dofus_unity'
New-Item -ItemType Directory -Path $target -Force | Out-Null
$rows = @(Import-Csv -LiteralPath $manifest -Delimiter ';' -Encoding UTF8)
$wanted = @($rows | Where-Object { $IncludeDofusLogo -or $_.role -ne 'reference_only' })
$all = @(Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Filter '*.png' -ErrorAction Stop)
$missing = @()
$copied = 0
foreach ($row in $wanted) {
    $expectedSuffix = '_' + $row.source_name
    $found = @($all | Where-Object { $_.Name.EndsWith($expectedSuffix, [System.StringComparison]::OrdinalIgnoreCase) })
    if ($found.Count -eq 0) {
        $missing += $row.source_name
        continue
    }
    if ($found.Count -gt 1) {
        throw "Fichier ambigu (plusieurs sources): $($row.source_name). Verifier manuellement : $($found.FullName -join ', ')"
    }
    $destDir = Join-Path $target $row.family
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    $destFile = Join-Path $destDir $row.source_name
    Copy-Item -LiteralPath $found[0].FullName -Destination $destFile -Force
    $copied++
}
if ($BackgroundPath) {
    if (!(Test-Path -LiteralPath $BackgroundPath -PathType Leaf)) { throw "Fond introuvable: $BackgroundPath" }
    $expected = '3834e92f6432019e2fde2b5f0ccb7f3b2236fda48ea7a6d368c60a660ef5fdeb'
    $actual = (Get-FileHash -LiteralPath $BackgroundPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Le fond ne correspond pas a la capture validee (SHA256 different)." }
    Copy-Item -LiteralPath $BackgroundPath -Destination (Join-Path $target 'selection_perso_original.png') -Force
}
$report = [ordered]@{
    source_root = $SourceRoot
    target = $target
    copied = $copied
    expected = $wanted.Count
    missing = $missing
    background_imported = [bool]$BackgroundPath
}
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'local-import-report.json') -Encoding UTF8
Write-Host "Assets Unity copies: $copied / $($wanted.Count)" -ForegroundColor Cyan
if ($missing.Count) {
    Write-Warning ("Introuvables : " + ($missing -join ', '))
    exit 2
}
Write-Host "Importer OK. Verifier droits de redistribution avant tout push public." -ForegroundColor Green

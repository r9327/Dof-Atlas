# Import non destructif des assets Unity depuis les sources personnelles.
# Installer les fichiers deja presents dans le checkout Dof-Atlas :
#   powershell -ExecutionPolicy Bypass -File tools/assets/import_dofus_unity_ui.ps1 -InstallPersonalTheme
# Ce mode ne modifie ni la distribution publique, ni les donnees du jeu.
[CmdletBinding()]
param(
    [string] $SourceRoot = (Join-Path $env:USERPROFILE 'Documents\Atlas-Dofus-UI-Composants'),
    [string] $BackgroundPath = '',
    [switch] $IncludeDofusLogo,
    [switch] $InstallPersonalTheme
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($InstallPersonalTheme) {
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA introuvable. Executer sur Windows.' }
    $sourceTheme = Join-Path $repo 'app\assets\themes\dofus_unity'
    $destination = Join-Path $env:LOCALAPPDATA 'DofusAtlas\themes\dofus_unity'
    $original = Join-Path $sourceTheme 'background_selection_original.png'
    $cleaned = Join-Path $destination 'background_selection_clean.png'
    $spriteFiles = @(Get-ChildItem -LiteralPath (Join-Path $sourceTheme 'sprites') -Filter '*.png' -File)
    $fontFiles = @(Get-ChildItem -LiteralPath (Join-Path $sourceTheme 'fonts') -Filter '*.ttf' -File)
    if (!(Test-Path -LiteralPath $original -PathType Leaf) -or
        $spriteFiles.Count -ne 46 -or $fontFiles.Count -ne 10) {
        throw 'Sources du theme incompletes dans ce checkout. Aucun theme active.'
    }
    foreach ($folder in @('sprites', 'fonts')) {
        $from = Join-Path $sourceTheme $folder
        $to = Join-Path $destination $folder
        New-Item -ItemType Directory -Path $to -Force | Out-Null
        Get-ChildItem -LiteralPath $from -File | ForEach-Object {
            $target = Join-Path $to $_.Name
            if (!(Test-Path -LiteralPath $target -PathType Leaf) -or
                (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne
                (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash) {
                Copy-Item -LiteralPath $_.FullName -Destination $target -Force
            }
        }
    }
    if (!(Test-Path -LiteralPath $cleaned -PathType Leaf)) {
        # Existing non-destructive helper verifies SHA and removes the HUD strip.
        Push-Location $repo
        try {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                & py -3.13 -m tools.assets.clean_unity_wallpaper --corner-toolbar --source $original --output $cleaned
                if ($LASTEXITCODE -ne 0 -and (Get-Command python -ErrorAction SilentlyContinue)) {
                    & python -m tools.assets.clean_unity_wallpaper --corner-toolbar --source $original --output $cleaned
                }
            } elseif (Get-Command python -ErrorAction SilentlyContinue) {
                & python -m tools.assets.clean_unity_wallpaper --corner-toolbar --source $original --output $cleaned
            } else {
                throw 'Python + Pillow sont requis pour nettoyer le fond local une seule fois.'
            }
            if ($LASTEXITCODE -ne 0) { throw 'Nettoyage du fond impossible (Python/Pillow ou SHA).' }
        } finally {
            Pop-Location
        }
    }
    if (!(Test-Path -LiteralPath $cleaned -PathType Leaf) -or
        (Get-Item -LiteralPath $cleaned).Length -lt 50000) {
        throw 'Fond nettoye absent ou incomplet. Aucun theme confirme.'
    }
    $installedSprites = @(Get-ChildItem -LiteralPath (Join-Path $destination 'sprites') -Filter '*.png' -File)
    $installedFonts = @(Get-ChildItem -LiteralPath (Join-Path $destination 'fonts') -Filter '*.ttf' -File)
    if ($installedSprites.Count -lt 46 -or $installedFonts.Count -lt 10) {
        throw 'Installation des sprites ou polices incomplete. Aucun theme confirme.'
    }
    # Marker records complete personal setup, without touching public manifests.
    Set-Content -LiteralPath (Join-Path $destination '.enabled') -Value 'personal-local-theme' -Encoding ascii
    Write-Host "Theme Unity personnel installe dans $destination" -ForegroundColor Green
    Write-Host 'Fermer puis relancer Dofus Atlas. Les assets sont preserves pendant les mises a jour.'
    return
}
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

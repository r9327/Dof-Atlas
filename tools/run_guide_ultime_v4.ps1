param(
    [string]$Class = "Huppermage",
    [ValidateSet("Ordre du Cœur Vaillant", "Ordre de l'Esprit Salvateur", "Ordre de l'Œil Attentif")]
    [string]$Order = "Ordre du Cœur Vaillant"
)

$ErrorActionPreference = "Stop"

py -3.13 .\tools\build_guide_ultime_final.py --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

py -3.13 .\tools\build_guide_ultime_gps_route.py `
    --alignment Bonta `
    --order $Order `
    --class $Class `
    --strict
exit $LASTEXITCODE

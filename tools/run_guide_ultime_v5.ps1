$ErrorActionPreference = "Stop"

Write-Host "[1/5] Guide Ultime V5 UNIVERSAL - tests"
py -3.13 -m unittest tests.test_guide_ultime_v5_scope tests.test_guide_ultime_v5_source_contract tests.test_guide_ultime_v5_or_runtime tests.test_guide_ultime_v3_policy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/5] Guide Ultime V5 UNIVERSAL - content lock STRICT"
py -3.13 .\tools\build_guide_ultime_final.py --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "Audit disponible: artifacts\guide_ultime_final_audit.json"
    exit $LASTEXITCODE
}

Write-Host "[3/5] Guide Ultime V5 UNIVERSAL - GPS SANITIZED FULL SUCCES STRICT"
py -3.13 -u .\tools\build_guide_ultime_gps_route_strict.py --strict
if ($LASTEXITCODE -ne 0) {
    if (Test-Path .\artifacts\guide_ultime_gps_route_audit.json) {
        Write-Host "Audit disponible: artifacts\guide_ultime_gps_route_audit.json"
    } elseif (Test-Path .\artifacts\guide_ultime_gps_crash.json) {
        Write-Host "Diagnostic GPS: artifacts\guide_ultime_gps_crash.json"
    } else {
        Write-Host "GPS en echec avant creation de l'audit et sans diagnostic."
    }
    exit $LASTEXITCODE
}

Write-Host "[4/5] Guide Ultime V5 UNIVERSAL - FORENSIC V2 + SAFE REPAIR STRICT"
py -3.13 -u .\tools\audit_guide_ultime_route_forensic_v2.py --repair-safe --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "FORENSIC V2 STRICT FAIL"
    Write-Host "Audit disponible: artifacts\guide_ultime_route_forensic_audit.json"
    Write-Host "Le Guide Ultime n'est PAS valide tant que cet audit n'est pas propre."
    exit $LASTEXITCODE
}

Write-Host "[5/5] Guide Ultime V5 UNIVERSAL - rangement artifacts"
py -3.13 .\tools\organize_guide_ultime_artifacts.py --apply
if ($LASTEXITCODE -ne 0) {
    Write-Host "Le guide est valide mais le rangement artifacts a echoue. Aucun artifact n'est supprime automatiquement."
    exit $LASTEXITCODE
}

Write-Host "V5 UNIVERSAL FORENSIC V2 STRICT PASS"
Write-Host "Audit contenu  : artifacts\guide_ultime_final_audit.json"
Write-Host "Audit GPS      : artifacts\guide_ultime_gps_route_audit.json"
Write-Host "Audit forensic : artifacts\guide_ultime_route_forensic_audit.json"
Write-Host "Artifacts      : anciens guide_ultime_* archives sous artifacts\archive\guide_ultime\"
exit 0

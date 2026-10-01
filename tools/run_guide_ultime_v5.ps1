$ErrorActionPreference = "Stop"

Write-Host "[1/5] Guide Ultime - tests"
py -3.13 -m unittest tests.test_guide_ultime_v5_scope tests.test_guide_ultime_manual_bonta_order tests.test_guide_ultime_v5_or_runtime tests.test_guide_ultime_v3_policy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/5] Guide Ultime - content lock STRICT"
py -3.13 -m tools.build_guide_ultime_final --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "Audit disponible: artifacts\guide_ultime_final_audit.json"
    exit $LASTEXITCODE
}

Write-Host "[3/5] Guide Ultime - GPS player-safe STRICT"
py -3.13 -u -m tools.guide_gps --strict
if ($LASTEXITCODE -ne 0) {
    if (Test-Path .\artifacts\guide_ultime_gps_route_audit.json) {
        Write-Host "Audit disponible: artifacts\guide_ultime_gps_route_audit.json"
    } elseif (Test-Path .\artifacts\guide_ultime_gps_crash.json) {
        Write-Host "Diagnostic GPS: artifacts\guide_ultime_gps_crash.json"
    }
    exit $LASTEXITCODE
}

Write-Host "[4/5] Guide Ultime - FORENSIC canonical + SAFE REPAIR STRICT"
py -3.13 -u -m tools.guide_forensic --repair-safe --strict
if ($LASTEXITCODE -ne 0) {
    Write-Host "FORENSIC STRICT FAIL"
    Write-Host "Audit disponible: artifacts\guide_ultime_route_forensic_audit.json"
    exit $LASTEXITCODE
}

Write-Host "[5/5] Guide Ultime - rangement artifacts"
py -3.13 -m tools.organize_guide_ultime_artifacts --apply
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "GUIDE STRICT PASS"
exit 0

param()

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$env:PYTHONUTF8 = "1"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "artifacts\ci_guide_ultime_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$OwnedValidationDir = $null
if (-not $env:DOFUS_ATLAS_VALIDATION_DATA_DIR) {
    $OwnedValidationDir = Join-Path ([IO.Path]::GetTempPath()) ("atlas-guide-data-" + [guid]::NewGuid().ToString("N"))
    $env:DOFUS_ATLAS_VALIDATION_DATA_DIR = $OwnedValidationDir
}
$ValidationLocal = Join-Path $env:DOFUS_ATLAS_VALIDATION_DATA_DIR "local"
New-Item -ItemType Directory -Force -Path $ValidationLocal | Out-Null
$ZaapSeed = Join-Path $Root "data\local\zaaps.json"
$ZaapSandbox = Join-Path $ValidationLocal "zaaps.json"
if ((Test-Path $ZaapSeed) -and -not (Test-Path $ZaapSandbox)) {
    Copy-Item -LiteralPath $ZaapSeed -Destination $ZaapSandbox
}

$results = [System.Collections.Generic.List[object]]::new()
$script:VerifiedFullStages = @{}

function Write-LogLine {
    param([string]$Path, [string]$Text)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff K"
    "[$stamp] $Text" | Tee-Object -FilePath $Path -Append
}

function Invoke-LoggedNative {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Executable,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )

    $safeName = ($Name -replace '[^A-Za-z0-9_.-]+', '_').Trim('_')
    $logPath = Join-Path $LogDir ("{0}.log" -f $safeName)
    if (Test-Path $logPath) { Remove-Item $logPath -Force }

    Write-Host ""
    Write-Host ("=" * 100)
    Write-Host "CI CHECK: $Name"
    Write-Host ("=" * 100)
    Write-LogLine -Path $logPath -Text "START $Name"
    Write-LogLine -Path $logPath -Text ("COMMAND: {0} {1}" -f $Executable, ($Arguments -join ' '))

    $started = Get-Date
    & $Executable @Arguments 2>&1 | Tee-Object -FilePath $logPath -Append
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 3)

    Write-LogLine -Path $logPath -Text "END $Name exit=$exitCode duration_s=$duration"
    $results.Add([pscustomobject]@{
        name = $Name
        exit_code = [int]$exitCode
        duration_seconds = $duration
        log = [IO.Path]::GetFileName($logPath)
    }) | Out-Null
}

$PythonExecutable = "python"
$PythonPrefixArguments = @()
if ($env:OS -eq "Windows_NT" -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $PythonExecutable = "py"
    $PythonPrefixArguments = @("-3.13")
}
elseif (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python introuvable. Installez Python 3.13 ou rendez 'python'/'py' accessible dans PATH."
    exit 1
}

function Invoke-PythonCheck {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )
    Invoke-LoggedNative $Name $PythonExecutable @($PythonPrefixArguments + $Arguments)
}

function Invoke-GuideTestOrReuse {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$Module
    )
    if ($script:VerifiedFullStages.ContainsKey($Name)) {
        $logPath = Join-Path $LogDir ("{0}.log" -f $Name)
        $proofCount = [int]$script:VerifiedFullStages[$Name]
        if (Test-Path $logPath) { Remove-Item $logPath -Force }
        Write-LogLine -Path $logPath -Text "REUSED_FROM_EXACT_FULL SHA=$env:GITHUB_SHA module=$Module tests=$proofCount"
        $results.Add([pscustomobject]@{
            name = $Name
            exit_code = 0
            duration_seconds = 0.0
            log = [IO.Path]::GetFileName($logPath)
            reused_from_full = $true
            exact_full_test_count = $proofCount
        }) | Out-Null
        return
    }
    Invoke-PythonCheck $Name @("-m", "unittest", $Module)
}

$diag = Join-Path $LogDir "00_environment.log"
if (Test-Path $diag) { Remove-Item $diag -Force }
Write-LogLine -Path $diag -Text "Guide Ultime CI diagnostics"
Write-LogLine -Path $diag -Text "ROOT=$Root"
Write-LogLine -Path $diag -Text "GITHUB_SHA=$env:GITHUB_SHA"
Write-LogLine -Path $diag -Text "GITHUB_REF=$env:GITHUB_REF"
Write-LogLine -Path $diag -Text "GITHUB_EVENT_NAME=$env:GITHUB_EVENT_NAME"
Write-LogLine -Path $diag -Text "RUNNER_OS=$env:RUNNER_OS"
Write-LogLine -Path $diag -Text ("PYTHON_COMMAND={0} {1}" -f $PythonExecutable, ($PythonPrefixArguments -join ' '))
Write-LogLine -Path $diag -Text "CATALOG_POLICY=CI may report Quest/Achievement catalogs unavailable; verified route contracts remain strict."

Push-Location $Root
try {
    "--- python --version ---" | Tee-Object -FilePath $diag -Append
    & $PythonExecutable @PythonPrefixArguments --version 2>&1 | Tee-Object -FilePath $diag -Append
    "--- pip --version ---" | Tee-Object -FilePath $diag -Append
    & $PythonExecutable @PythonPrefixArguments -m pip --version 2>&1 | Tee-Object -FilePath $diag -Append
    "--- git status ---" | Tee-Object -FilePath $diag -Append
    & git status --short --branch 2>&1 | Tee-Object -FilePath $diag -Append
    "--- git lfs status ---" | Tee-Object -FilePath $diag -Append
    & git lfs status 2>&1 | Tee-Object -FilePath $diag -Append
    "--- canonical route files ---" | Tee-Object -FilePath $diag -Append
    Get-ChildItem "data\routes\guide_ultime_manual" -File | Sort-Object Name | Select-Object -ExpandProperty Name | Tee-Object -FilePath $diag -Append

    # Optional, same-checkout FULL proof. Every missing or ambiguous test
    # causes a normal, independent subprocess run of ALL Guide test modules.
    if ($env:ATLAS_GUIDE_REUSE_FULL -eq "1" -and
        $env:ATLAS_FULL_SUITE_SUCCESS -eq "success" -and
        -not [string]::IsNullOrWhiteSpace($env:GITHUB_SHA)) {
        $proofPath = Join-Path $LogDir "exact_full_test_proof.json"
        $fullLog = Join-Path $Root "artifacts/ci_app_logs/05_full_unittest.log"
        & $PythonExecutable @PythonPrefixArguments -m tools.ci_guide_full_evidence --root $Root --log $fullLog --sha $env:GITHUB_SHA --out $proofPath
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $proofPath)) {
            $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
            if ($proof.status -eq "PROVEN" -and $proof.head -eq $env:GITHUB_SHA) {
                $required = @("11_existing_guides_tests", "12_existing_success_tests", "13_existing_shell_tests")
                foreach ($name in $required) {
                    if ($proof.stages.PSObject.Properties.Name -contains $name -and [int]$proof.stages.$name -gt 0) {
                        $script:VerifiedFullStages[$name] = [int]$proof.stages.$name
                    }
                }
                if ($script:VerifiedFullStages.Count -ne $required.Count) {
                    $script:VerifiedFullStages = @{}
                }
            }
        }
        if ($script:VerifiedFullStages.Count -ne 3) {
            Write-Warning "Guide exact FULL evidence unavailable: execute original suites."
        }
    }

    Invoke-PythonCheck "01_install_dependencies" @("-m", "pip", "install", "-r", "requirements-pyside.txt")

    Invoke-PythonCheck "02_guide_ultime_core_tests" @(
        "-m", "unittest",
        "tests.test_guide_ultime_v5_ui",
        "tests.test_guide_ultime_v5_runtime",
        "tests.test_guide_ultime_walkthrough",
        "tests.test_guide_ultime_route_sanitizer",
        "tests.test_guide_ultime_route_sheet_ui",
        "tests.test_guide_ultime_manual_preview",
        "tests.test_guide_ultime_manual_ui_navigation",
        "tests.test_guide_ultime_manual_success_sync",
        "tests.test_guide_ultime_success_links",
        "tests.test_guide_ultime_manual_class_branch",
        "tests.test_guide_ultime_manual_runtime_text",
        "tests.test_guide_ultime_manual_prerequisites",
        "tests.test_guide_ultime_manual_route_hooks",
        "tests.test_guide_ultime_manual_structured_domain",
        "tests.test_guide_ultime_auto_validation_contract",
        "tests.test_guide_ultime_canonical_lock",
        "tests.test_guide_ultime_action_review_audit",
        "tests.test_guide_ultime_action_quality_audit",
        "tests.test_guide_ultime_stable_progress_keys",
        "tests.test_guide_progress_persistence",
        "tests.test_home_guide_ultime_source",
        "tests.test_quest_detail_guide_ui_contract",
        "tests.test_guide_ultime_ocre_registry_runtime"
    )

    Invoke-PythonCheck "03_manual_route_composition_tests" @(
        "-m", "unittest",
        "tests.test_guide_ultime_manual_route_composition",
        "tests.test_guide_ultime_manual_stage_imports",
        "tests.test_guide_ultime_manual_astrub_v6",
        "tests.test_guide_ultime_manual_boss_fusions",
        "tests.test_guide_ultime_temporal_registry",
        "tests.test_guide_ultime_manual_level_191_200",
        "tests.test_guide_ultime_manual_level_191_200_v4",
        "tests.test_guide_ultime_manual_level_191_200_v5",
        "tests.test_guide_ultime_manual_post_200"
    )

    Invoke-PythonCheck "03b_canonical_lock_audit" @("-m", "tools.audit_guide_ultime_canonical_lock", "--strict", "--output", ".\artifacts\ci_guide_ultime_logs\canonical_lock.json")
    Invoke-PythonCheck "03c_canonical_dependency_audit" @("-m", "tools.audit_guide_ultime_canonical_dependencies", "--strict", "--output", ".\artifacts\ci_guide_ultime_logs\canonical_dependencies.json")
    Invoke-PythonCheck "04_structural_audit" @("-m", "tools.validate_guide_ultime_manual_bundle", "--strict", "--skip-catalog")
    Invoke-PythonCheck "05_transversal_canonical_audit" @("-m", "tools.validate_guide_ultime_manual_transversals", "--strict", "--skip-catalog")
    Invoke-PythonCheck "06_route_hook_resolution" @("-m", "tools.audit_guide_ultime_manual_route_hooks", "--strict")
    Invoke-PythonCheck "07_prerequisite_order_audit" @(
        "-m", "tools.audit_guide_ultime_manual_prerequisites",
        "--strict",
        "--output", ".\artifacts\ci_guide_ultime_logs\prerequisite_order.json"
    )
    Invoke-PythonCheck "08_light_coverage_audit" @("-m", "tools.audit_guide_ultime_manual_coverage")
    Invoke-PythonCheck "09_final_success_coverage_audit" @(
        "-m", "tools.audit_guide_ultime_manual_final_coverage",
        "--strict",
        "--output", ".\artifacts\ci_guide_ultime_logs\final_coverage.json"
    )
    Invoke-PythonCheck "10_runtime_audit" @("-m", "tools.audit_guide_ultime_manual_runtime", "--strict-fields")
    Invoke-PythonCheck "10b_action_quality_inventory" @("-m", "tools.audit_guide_ultime_action_quality", "--strict-hard", "--output", ".\artifacts\ci_guide_ultime_logs\action_quality.json")
    Invoke-PythonCheck "10c_player_contract_7e" @("-m", "tools.guide_player_contract", "--strict-hard", "--output", ".\artifacts\ci_guide_ultime_logs\player_contract_7e.json")

    Invoke-GuideTestOrReuse "11_existing_guides_tests" "tests.test_guides_phase3"
    Invoke-GuideTestOrReuse "12_existing_success_tests" "tests.test_achievements_lot7"
    Invoke-GuideTestOrReuse "13_existing_shell_tests" "tests.test_pyside_shell"
}
finally {
    Pop-Location
    if ($OwnedValidationDir) {
        Remove-Item -LiteralPath $OwnedValidationDir -Recurse -Force
        Remove-Item Env:\DOFUS_ATLAS_VALIDATION_DATA_DIR
    }
}

$summaryJson = Join-Path $LogDir "ci_summary.json"
$summaryTxt = Join-Path $LogDir "ci_summary.txt"
$failed = @($results | Where-Object { $_.exit_code -ne 0 })
$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString("o")
    github_sha = $env:GITHUB_SHA
    github_ref = $env:GITHUB_REF
    total_checks = $results.Count
    failed_checks = $failed.Count
    status = if ($failed.Count -eq 0) { "PASS" } else { "FAIL" }
    checks = $results
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryJson

@(
    "Guide Ultime CI: $($summary.status)",
    "Commit: $env:GITHUB_SHA",
    "Checks: $($results.Count)",
    "Failures: $($failed.Count)",
    "",
    ($results | ForEach-Object { "[{0}] {1} (exit={2}, {3}s) -> {4}" -f ($(if ($_.exit_code -eq 0) { 'OK' } else { 'FAIL' })), $_.name, $_.exit_code, $_.duration_seconds, $_.log })
) | Set-Content -Encoding UTF8 $summaryTxt

Get-Content $summaryTxt | Write-Host

if ($env:GITHUB_STEP_SUMMARY) {
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "## Guide Ultime CI - $($summary.status)"
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value ""
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "Commit: ``$env:GITHUB_SHA``  "
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "Checks: $($results.Count) - Failures: $($failed.Count)"
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value ""
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "| Check | Exit | Log |"
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "|---|---:|---|"
    foreach ($row in $results) {
        Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value "| $($row.name) | $($row.exit_code) | $($row.log) |"
    }
}

if ($failed.Count -gt 0) {
    Write-Error "Guide Ultime CI failed: $($failed.Count) check(s) failed. Logs are in $LogDir."
    exit 1
}

exit 0

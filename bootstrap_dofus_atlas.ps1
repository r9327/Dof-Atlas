param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSCommandPath
$LogDir = Join-Path $Root "logs"
$DataDir = Join-Path $Root "data"
$LogFile = Join-Path $LogDir "bootstrap_prereqs.log"
$StatusFile = Join-Path $DataDir "bootstrap_status.txt"
$RequirementsFile = Join-Path $Root "requirements-pyside.txt"
$AppScript = Join-Path $Root "main.py"

$PythonPackageId = "Python.Python.3.13"
$PythonPackageVersion = "3.13.15"
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe"
$PythonInstallerSha256 = "edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403"

New-Item -ItemType Directory -Force -Path $LogDir, $DataDir | Out-Null

function Write-AtlasLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Show-AtlasPopup {
    param(
        [string]$Message,
        [int]$Seconds = 2
    )
    try {
        $shell = New-Object -ComObject WScript.Shell
        $null = $shell.Popup($Message, $Seconds, "Dofus Atlas", 64)
    } catch {
        Write-AtlasLog "Notification impossible: $($_.Exception.Message)"
    }
}

function Set-AtlasStatus {
    param(
        [string]$Message,
        [switch]$Popup,
        [int]$Seconds = 2
    )
    Set-Content -Path $StatusFile -Value $Message -Encoding UTF8
    Write-AtlasLog $Message
    if ($Popup) {
        Show-AtlasPopup -Message $Message -Seconds $Seconds
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($machinePath, $userPath, $env:Path) -join ";"
}

function Test-Python313 {
    param([string]$PythonExe)
    if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
        return $false
    }
    try {
        & $PythonExe -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Resolve-Python313 {
    Refresh-ProcessPath
    $fixedCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:ProgramFiles "Python313\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python313\python.exe")
    )
    foreach ($candidate in $fixedCandidates) {
        if (Test-Python313 $candidate) {
            $pythonw = Join-Path (Split-Path -Parent $candidate) "pythonw.exe"
            return [pscustomobject]@{
                PythonExe = $candidate
                LaunchExe = $(if (Test-Path $pythonw) { $pythonw } else { $candidate })
                LaunchArgsPrefix = @()
            }
        }
    }

    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $pythonExe = (& $pyLauncher.Source -3.13 -c "import sys; print(sys.executable)" 2>$null).Trim()
            if (Test-Python313 $pythonExe) {
                $pythonw = Join-Path (Split-Path -Parent $pythonExe) "pythonw.exe"
                if (Test-Path $pythonw) {
                    return [pscustomobject]@{
                        PythonExe = $pythonExe
                        LaunchExe = $pythonw
                        LaunchArgsPrefix = @()
                    }
                }
                $pywLauncher = Get-Command "pyw.exe" -ErrorAction SilentlyContinue
                if ($pywLauncher) {
                    return [pscustomobject]@{
                        PythonExe = $pythonExe
                        LaunchExe = $pywLauncher.Source
                        LaunchArgsPrefix = @("-3.13")
                    }
                }
                return [pscustomobject]@{
                    PythonExe = $pythonExe
                    LaunchExe = $pythonExe
                    LaunchArgsPrefix = @()
                }
            }
        } catch {
            Write-AtlasLog "Launcher Python indisponible: $($_.Exception.Message)"
        }
    }
    return $null
}

function Invoke-HiddenProcess {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory = $Root,
        [int]$TimeoutSeconds = 900
    )
    Write-AtlasLog ("Commande: {0} {1}" -f $FilePath, ($ArgumentList -join " "))
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Commande echouee ($($process.ExitCode)): $FilePath"
    }
}

function Install-WingetPackage {
    param(
        [string]$PackageId,
        [string]$Version,
        [string]$Label
    )
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget indisponible"
    }
    Set-AtlasStatus "Prechargement: installation silencieuse de $Label..."
    $args = @(
        "install",
        "--id", $PackageId,
        "--version", $Version,
        "--exact",
        "--source", "winget",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements"
    )
    Invoke-HiddenProcess -FilePath $winget.Source -ArgumentList $args -TimeoutSeconds 1200
}

function Install-PythonFallback {
    Set-AtlasStatus "Prechargement: telechargement Python $PythonPackageVersion..."
    $installer = Join-Path $env:TEMP "dofus-atlas-python-3.13.exe"
    try {
        Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $installer -UseBasicParsing
        $actualHash = (Get-FileHash -Path $installer -Algorithm SHA256).Hash.ToLowerInvariant()
        $expectedHash = $PythonInstallerSha256.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "empreinte SHA-256 Python invalide (attendu=$expectedHash obtenu=$actualHash)"
        }
        Write-AtlasLog "Installeur Python SHA-256 valide: $actualHash"
        Set-AtlasStatus "Prechargement: installation silencieuse Python $PythonPackageVersion..."
        Invoke-HiddenProcess -FilePath $installer -ArgumentList @("/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "Include_pip=1", "Include_test=0") -TimeoutSeconds 1200
    } finally {
        if (Test-Path $installer) {
            Remove-Item -Force $installer -ErrorAction SilentlyContinue
        }
    }
}

function Ensure-Python {
    $runtime = Resolve-Python313
    if ($runtime) {
        Write-AtlasLog "Python 3.13 trouve: $($runtime.PythonExe)"
        return $runtime
    }

    try {
        Install-WingetPackage -PackageId $PythonPackageId -Version $PythonPackageVersion -Label "Python $PythonPackageVersion"
    } catch {
        Write-AtlasLog "Installation Python via winget impossible: $($_.Exception.Message)"
        Install-PythonFallback
    }

    Refresh-ProcessPath
    $runtime = Resolve-Python313
    if (-not $runtime) {
        throw "Python 3.13 reste introuvable apres installation"
    }
    Write-AtlasLog "Python 3.13 installe: $($runtime.PythonExe)"
    return $runtime
}

function Test-PythonModules {
    param([object]$Runtime)
    try {
        & $Runtime.PythonExe -c "import PIL.Image; import PySide6.QtWidgets; import PySide6.QtWebEngineWidgets; import pyautogui; import win32gui" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Ensure-Pip {
    param([object]$Runtime)
    & $Runtime.PythonExe -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return
    }
    & $Runtime.PythonExe -m ensurepip --upgrade 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "ensurepip a echoue"
    }
}

function Ensure-PythonModules {
    param([object]$Runtime)
    if (Test-PythonModules -Runtime $Runtime) {
        Write-AtlasLog "Modules Python OK: PySide6, QtWebEngine, Pillow, pyautogui, pywin32"
        return
    }
    if (-not (Test-Path $RequirementsFile)) {
        throw "requirements-pyside.txt introuvable"
    }
    Set-AtlasStatus "Prechargement: installation silencieuse des modules Python..."
    Ensure-Pip -Runtime $Runtime
    & $Runtime.PythonExe -m pip install --disable-pip-version-check --quiet --require-hashes --no-deps -r $RequirementsFile 2>&1 | Add-Content -Path $LogFile -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "installation requirements-pyside.txt echouee"
    }
    if (-not (Test-PythonModules -Runtime $Runtime)) {
        throw "modules Python toujours indisponibles apres installation"
    }
}

function Start-DofusAtlas {
    param([object]$Runtime)
    if (-not (Test-Path $AppScript)) {
        throw "main.py introuvable"
    }
    $args = @()
    $args += $Runtime.LaunchArgsPrefix
    $args += @("-B", $AppScript)
    Write-AtlasLog ("Lancement app: {0} {1}" -f $Runtime.LaunchExe, ($args -join " "))
    Start-Process -FilePath $Runtime.LaunchExe -ArgumentList $args -WorkingDirectory $Root -WindowStyle Hidden
}

try {
    Set-AtlasStatus "Prechargement: verification des prerequis..."
    $runtime = Ensure-Python
    Ensure-PythonModules -Runtime $runtime
    Set-AtlasStatus "Prechargement: prerequis OK, lancement de Dofus Atlas."
    if (-not $NoLaunch) {
        Start-DofusAtlas -Runtime $runtime
    }
    exit 0
} catch {
    $message = "Prechargement bloque: $($_.Exception.Message)"
    Set-AtlasStatus $message -Popup -Seconds 8
    Write-AtlasLog $_.ScriptStackTrace
    exit 1
}

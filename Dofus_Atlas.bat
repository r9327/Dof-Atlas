@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Dofus Atlas - Launcher
color 0B
mode con: cols=42 lines=9 >nul 2>&1

set "ROOT=%~dp0"
set "LOG_DIR=%ROOT%logs"
set "LOG_FILE=%LOG_DIR%\start_log.txt"
set "APP_SCRIPT=%ROOT%launch.py"
set "INSTALLER=%ROOT%Install_Dofus_Atlas.bat"
set "PYTHON_EXE="
set "PYTHONW_EXE="

if not defined DOFUS_ATLAS_STARTUP_PROFILE set "DOFUS_ATLAS_STARTUP_PROFILE=1"
if not defined DOFUS_ATLAS_STARTUP_PROFILE_FILE set "DOFUS_ATLAS_STARTUP_PROFILE_FILE=%LOG_DIR%\startup_profile.jsonl"
set "DOFUS_ATLAS_LAUNCHER_STARTED_AT=%date% %time%"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

> "%LOG_FILE%" echo START
>> "%LOG_FILE%" echo LAUNCHER_START %DOFUS_ATLAS_LAUNCHER_STARTED_AT%

call :banner
call :step "Verification des prerequis"

if not exist "%APP_SCRIPT%" (
    call :error "APP_SCRIPT_MISSING" "launch.py introuvable."
    exit /b 1
)

call :find_python
if "%PYTHON_EXE%"=="" (
    call :error "PYTHON_MISSING" "Python 3.13 introuvable. Lance Install_Dofus_Atlas.bat pour installer ou reparer les prerequis."
    exit /b 1
)

if "%PYTHONW_EXE%"=="" set "PYTHONW_EXE=%PYTHON_EXE%"

call :ok "Python 3.13 detecte"
>> "%LOG_FILE%" echo PYTHON_OK %date% %time%

call :step "Verification de l'environnement et du code"
>> "%LOG_FILE%" echo PREFLIGHT_CHECK %date% %time%
"%PYTHON_EXE%" -m app.startup_preflight "%APP_SCRIPT%" >> "%LOG_FILE%" 2>&1
set "PREFLIGHT_CODE=%errorlevel%"
if "%PREFLIGHT_CODE%"=="10" (
    call :error "MODULES_MISSING" "Environnement Python incomplet. Lance Install_Dofus_Atlas.bat pour installer ou reparer les dependances."
    exit /b 1
)
if "%PREFLIGHT_CODE%"=="20" (
    call :error "SYNTAX_FAILED" "Erreur de syntaxe dans launch.py."
    exit /b 1
)
if not "%PREFLIGHT_CODE%"=="0" (
    call :error "PREFLIGHT_FAILED" "Verification de lancement impossible. Consulte logs\start_log.txt."
    exit /b 1
)
call :ok "Environnement et code valides"
>> "%LOG_FILE%" echo PREFLIGHT_OK %date% %time%

echo.
call :step "Lancement de Dofus Atlas"
>> "%LOG_FILE%" echo APP_START %date% %time%
>> "%LOG_FILE%" echo LAUNCH_CMD="%PYTHONW_EXE%" "%APP_SCRIPT%"

start "" "%PYTHONW_EXE%" "%APP_SCRIPT%"

call :ok "Dofus Atlas demarre"
>> "%LOG_FILE%" echo APP_START_SENT %date% %time%
endlocal
exit /b 0


:find_python
set "PYTHON_EXE="
set "PYTHONW_EXE="
if exist "%ROOT%.venv\Scripts\python.exe" (
    call :use_python_if_313 "%ROOT%.venv\Scripts\python.exe"
    if not "!PYTHON_EXE!"=="" exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    call :use_python_if_313 "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    if not "!PYTHON_EXE!"=="" exit /b 0
)

if exist "%ProgramFiles%\Python313\python.exe" (
    call :use_python_if_313 "%ProgramFiles%\Python313\python.exe"
    if not "!PYTHON_EXE!"=="" exit /b 0
)

for /f "delims=" %%P in ('py -3.13 -c "import sys; ok=sys.version_info[0] == 3 and sys.version_info[1] == 13; print(sys.executable) if ok else sys.exit(1)" 2^>nul') do (
    if exist "%%P" (
        call :use_python_if_313 "%%P"
        if not "!PYTHON_EXE!"=="" exit /b 0
    )
)

for /f "delims=" %%P in ('py -3 -c "import sys; ok=sys.version_info[0] == 3 and sys.version_info[1] == 13; print(sys.executable) if ok else sys.exit(1)" 2^>nul') do (
    if exist "%%P" (
        call :use_python_if_313 "%%P"
        if not "!PYTHON_EXE!"=="" exit /b 0
    )
)

for /f "delims=" %%P in ('python -c "import sys; ok=sys.version_info[0] == 3 and sys.version_info[1] == 13; print(sys.executable) if ok else sys.exit(1)" 2^>nul') do (
    if exist "%%P" (
        call :use_python_if_313 "%%P"
        if not "!PYTHON_EXE!"=="" exit /b 0
    )
)

exit /b 0


:use_python_if_313
if not exist "%~1" exit /b 1
"%~1" -c "import sys; ok=sys.version_info[0] == 3 and sys.version_info[1] == 13; print(sys.version.split()[0]) if ok else None; raise SystemExit(0 if ok else 1)" >> "%LOG_FILE%" 2>&1
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%~1"
for %%D in ("%~dp1pythonw.exe") do if exist "%%~fD" set "PYTHONW_EXE=%%~fD"
exit /b 0


:banner
cls
echo.
echo  DOFUS ATLAS
echo  Launcher
echo.
exit /b 0


:step
echo  [..] %~1
exit /b 0


:ok
echo  [OK] %~1
exit /b 0


:warn
echo  [!!] %~1
exit /b 0


:error
echo.
echo  +----------------------------------------------------+
echo  ^| ERREUR                                             ^|
echo  +----------------------------------------------------+
echo  %~2
echo.
echo  Installation / reparation : Install_Dofus_Atlas.bat
echo  Log : logs\start_log.txt
echo.
>> "%LOG_FILE%" echo ERROR: %~1
>> "%LOG_FILE%" echo DETAIL: %~2
timeout /t 8 /nobreak >nul
exit /b 1

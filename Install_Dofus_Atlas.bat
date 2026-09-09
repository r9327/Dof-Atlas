@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Dofus Atlas - Installation

set "ROOT=%~dp0"
set "BOOTSTRAP=%ROOT%bootstrap_dofus_atlas.ps1"

if not exist "%BOOTSTRAP%" (
    echo.
    echo  ERREUR: bootstrap_dofus_atlas.ps1 introuvable.
    echo.
    pause
    exit /b 1
)

echo.
echo  DOFUS ATLAS - INSTALLATION / REPARATION
echo.
echo  Ce script peut installer Python 3.13 et les dependances Python.
echo  Le launcher normal Dofus_Atlas.bat ne modifie jamais l'environnement.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BOOTSTRAP%" -NoLaunch
if errorlevel 1 (
    echo.
    echo  Installation ou reparation echouee.
    echo  Consulte logs\bootstrap_prereqs.log
    echo.
    pause
    exit /b 1
)

echo.
echo  Installation / reparation terminee.
echo  Tu peux maintenant lancer Dofus_Atlas.bat.
echo.
pause
endlocal
exit /b 0

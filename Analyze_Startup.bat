@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Dofus Atlas - Startup Report

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0tools\analyze_startup.py"
    goto :done
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%~dp0tools\analyze_startup.py"
    goto :done
)

py -3.13 "%~dp0tools\analyze_startup.py" 2>nul
if not errorlevel 1 goto :done

python "%~dp0tools\analyze_startup.py"
if not errorlevel 1 goto :done

echo.
echo Python 3.13 introuvable. Lance Dofus_Atlas.bat ou Install_Dofus_Atlas.bat d'abord.

:done
echo.
pause
endlocal

@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "ROOT=%CD%\"

title Dofus Atlas - Startup Report

if exist "%ROOT%.venv\Scripts\python.exe" (
    "%ROOT%.venv\Scripts\python.exe" "%ROOT%tools\analyze_startup.py"
    goto :done
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%ROOT%tools\analyze_startup.py"
    goto :done
)

py -3.13 "%ROOT%tools\analyze_startup.py" 2>nul
if not errorlevel 1 goto :done

python "%ROOT%tools\analyze_startup.py"
if not errorlevel 1 goto :done

echo.
echo Python 3.13 introuvable. Lance DOFUS.bat ou scripts\windows\Install_Dofus_Atlas.bat d'abord.

:done
echo.
pause
endlocal

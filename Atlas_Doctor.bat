@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ^(py^) introuvable.
  pause
  exit /b 1
)
py -3.13 tools\atlas_doctor.py
set "ATLAS_DOCTOR_EXIT=%ERRORLEVEL%"
if not "%ATLAS_DOCTOR_EXIT%"=="0" echo Atlas Doctor a termine avec le code %ATLAS_DOCTOR_EXIT%.
pause
exit /b %ATLAS_DOCTOR_EXIT%

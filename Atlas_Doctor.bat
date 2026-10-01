@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher ^(py^) introuvable.
  pause
  exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
  echo Git introuvable : verification des hooks ignoree.
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\install_git_hooks.ps1 -RepoRoot "%CD%"
  if errorlevel 1 echo Git hooks setup ....... FAIL
)

py -3.13 -m tools.atlas_doctor %*
set "ATLAS_DOCTOR_EXIT=%ERRORLEVEL%"
if not "%ATLAS_DOCTOR_EXIT%"=="0" echo Atlas Doctor a termine avec le code %ATLAS_DOCTOR_EXIT%.
pause
exit /b %ATLAS_DOCTOR_EXIT%

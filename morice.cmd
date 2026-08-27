@echo off
setlocal

set "ROOT=%~dp0"
set "VENV_PYTHONW=%ROOT%.venv\Scripts\pythonw.exe"
set "VENV_PYTHON=%ROOT%.venv\Scripts\python.exe"
set "EXE=%ROOT%dist\MORICE\MORICE.exe"

if not "%MORICE_FORCE_PACKAGED%"=="1" if exist "%VENV_PYTHONW%" (
  start "" /D "%ROOT%" "%VENV_PYTHONW%" "%ROOT%morice_app_launcher.py"
  exit /b 0
)

if not "%MORICE_FORCE_PACKAGED%"=="1" if exist "%VENV_PYTHON%" (
  "%VENV_PYTHON%" "%ROOT%morice_app_launcher.py"
  exit /b %ERRORLEVEL%
)

if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)

where python3.12 >nul 2>nul
if %ERRORLEVEL%==0 (
  python3.12 "%ROOT%morice_app_launcher.py"
  exit /b %ERRORLEVEL%
)

python "%ROOT%morice_app_launcher.py"

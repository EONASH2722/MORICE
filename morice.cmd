@echo off
setlocal

set "ROOT=%~dp0"
set "EXE=%ROOT%dist\MORICE\MORICE.exe"

if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)

python -m morice.pyside_app

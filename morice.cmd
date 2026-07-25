@echo off
setlocal

set "ROOT=%~dp0"
set "VNEXT_EXE=%ROOT%dist-vnext\MORICE\MORICE.exe"
set "EXE=%ROOT%dist\MORICE\MORICE.exe"

if exist "%VNEXT_EXE%" (
  start "" "%VNEXT_EXE%"
  exit /b 0
)

if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)

python -m morice.pyside_app

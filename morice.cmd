@echo off
setlocal

set "ROOT=%~dp0"
set "EXE=%ROOT%dist\MORICE\MORICE.exe"

if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)

py -3.12 -m morice.pyside_app

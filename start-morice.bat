@echo off
cd /d "%~dp0"
if not exist "node_modules\electron" (
  echo Installing Morice desktop runtime...
  npm.cmd install
)
echo Starting Morice desktop app...
npm.cmd start

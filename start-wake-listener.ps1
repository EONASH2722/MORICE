$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "morice_wake_listener.py"
Start-Process -FilePath "py" -ArgumentList @("-3.12", $script) -WorkingDirectory $root -WindowStyle Hidden

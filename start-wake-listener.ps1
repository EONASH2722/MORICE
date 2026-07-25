$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "morice_wake_listener.py"

$pythonCommand = $null
foreach ($candidate in @("py", "python", "python3")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pythonCommand = $candidate
        break
    }
}

if (-not $pythonCommand) {
    throw "Could not find a Python interpreter to start the wake listener."
}

if ($pythonCommand -eq "py") {
    try {
        Start-Process -FilePath "py" -ArgumentList @("-3.12", $script) -WorkingDirectory $root -WindowStyle Hidden
        exit 0
    } catch {
        Start-Process -FilePath "py" -ArgumentList @($script) -WorkingDirectory $root -WindowStyle Hidden
        exit 0
    }
}

Start-Process -FilePath $pythonCommand -ArgumentList @($script) -WorkingDirectory $root -WindowStyle Hidden

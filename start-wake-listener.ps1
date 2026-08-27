$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "morice_wake_listener.py"
$venvPython = Join-Path $root ".venv\Scripts\pythonw.exe"

# The wake daemon performs keyword/double-clap detection only. It automatically
# releases the microphone while Live Action owns STT, then resumes after Voice
# exits. Set MORICE_ENABLE_ALWAYS_ON_WAKE=0 to opt out entirely.
$alwaysOnWake = [string]$env:MORICE_ENABLE_ALWAYS_ON_WAKE
if ($alwaysOnWake.Trim().ToLowerInvariant() -in @("0", "false", "no", "off", "disabled")) {
    exit 0
}

if (Test-Path -LiteralPath $venvPython) {
    Start-Process -FilePath $venvPython -ArgumentList @($script) -WorkingDirectory $root -WindowStyle Hidden
    exit 0
}

$pythonCommand = $null
foreach ($candidate in @("python3.12", "py", "python", "python3")) {
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

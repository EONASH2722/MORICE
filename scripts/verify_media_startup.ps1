# Explicit local executable probe from a fresh directory outside the checkout.
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$profileRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('MORICE-phase9-profile-' + [guid]::NewGuid().ToString('N'))
if ([System.IO.Path]::GetFullPath($profileRoot).StartsWith([System.IO.Path]::GetFullPath($workspaceRoot), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The isolated probe directory must be outside the checkout.'
}
New-Item -ItemType Directory -Path $profileRoot | Out-Null
$env:APPDATA = Join-Path $profileRoot 'AppData'
$env:LOCALAPPDATA = Join-Path $profileRoot 'LocalAppData'
$env:MORICE_RUNTIME_DIR = Join-Path $profileRoot 'runtime'
$env:MORICE_LOCAL_DATA_DIR = Join-Path $profileRoot 'data'
foreach ($variableName in @('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX')) {
    Remove-Item -LiteralPath ('Env:\' + $variableName) -ErrorAction SilentlyContinue
}
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
$executable = Join-Path $workspaceRoot 'build\phase9-frozen-clean\MORICE\MORICE.exe'
$probeOutput = Join-Path $profileRoot 'frozen-smoke.json'
$launcherClock = [System.Diagnostics.Stopwatch]::StartNew()
$probeProcess = Start-Process -FilePath $executable -ArgumentList '--morice-smoke-test', $probeOutput -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru
if (-not $probeProcess.WaitForExit(45000)) {
    Stop-Process -Id $probeProcess.Id
    throw 'The owned isolated package probe exceeded 45 seconds.'
}
$launcherClock.Stop()
$probe = Get-Content -LiteralPath $probeOutput -Raw | ConvertFrom-Json
if ($probeProcess.ExitCode -ne 0 -or $probe.critical_failures -ne 0 -or $probe.leases_after -ne 0 -or -not $probe.shutdown.clean -or $probe.health.Count -lt 20) {
    throw 'The isolated package probe failed its recorded health/cleanup contract.'
}
Copy-Item -LiteralPath $probeOutput -Destination (Join-Path $workspaceRoot 'build\phase9-isolated-startup-smoke.json')
$receipt = [ordered]@{
    executable = $executable
    executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    cwd = $profileRoot
    system_path_only = $true
    python_environment_removed = $true
    process_launch_to_exit_ms = $launcherClock.Elapsed.TotalMilliseconds
    startup_and_three_second_probe_ms = $probe.startup_and_probe_ms
    health_checks = $probe.health.Count
    critical_failures = $probe.critical_failures
    ui_ticks = $probe.ui_ticks
    clean_shutdown = $probe.shutdown.clean
    leases_after = $probe.leases_after
    exit_code = $probeProcess.ExitCode
    original_smoke_file = $probeOutput
}
$json = $receipt | ConvertTo-Json -Depth 4
Set-Content -LiteralPath (Join-Path $workspaceRoot 'build\phase9-release-startup.json') -Value $json -Encoding utf8
$json

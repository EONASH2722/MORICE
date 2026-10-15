param(
    [Parameter(Mandatory=$true)][ValidateSet('Frozen','Regression','Wheel')][string]$Task,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]+$')][string]$RunName
)
# One owned validation job. Receipt and redirected logs survive the sending shell.
$ErrorActionPreference = 'Stop'
$taskWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskWorkspace '.venv\Scripts\python.exe'
$taskBuild = Join-Path $taskWorkspace 'build'
$taskLog = Join-Path $taskBuild "$RunName-$Task.log"
$taskReceipt = Join-Path $taskBuild "$RunName-$Task.json"
foreach ($target in @($taskLog,$taskReceipt)) {
    $absolute = [IO.Path]::GetFullPath($target)
    if (-not $absolute.StartsWith($taskBuild + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Validation output is outside the workspace build directory.' }
}
Set-Location -LiteralPath $taskWorkspace
$taskSource = & $taskPython -c "import hashlib;from pathlib import Path;r=Path.cwd();h=hashlib.sha256();[(h.update(str(p.relative_to(r)).encode()),h.update(p.read_bytes())) for p in sorted((r/'morice').rglob('*.py'))];print(h.hexdigest())"
if ($LASTEXITCODE -ne 0) { throw 'Cannot fingerprint the validation source.' }
$taskRecord = [ordered]@{ task=$Task; run=$RunName; status='RUNNING'; helper_pid=$PID;
    source_sha256=$taskSource.Trim(); started_utc=[DateTime]::UtcNow.ToString('o');
    log=$taskLog; workspace=$taskWorkspace; public_actions_taken=$false }
if ($Task -eq 'Regression') {
    $taskTestSource = & $taskPython -c "import hashlib;from pathlib import Path;r=Path.cwd();h=hashlib.sha256();[(h.update(str(p.relative_to(r)).encode()),h.update(p.read_bytes())) for p in sorted((r/'tests').rglob('*.py'))];print(h.hexdigest())"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot fingerprint the validation tests.' }
    $taskRecord['test_source_sha256'] = $taskTestSource.Trim()
}
function Save-ValidationReceipt {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($taskRecord | ConvertTo-Json -Depth 5))
    $stream = [IO.FileStream]::new($taskReceipt,[IO.FileMode]::Create,[IO.FileAccess]::Write,
        [IO.FileShare]::Read,4096,[IO.FileOptions]::WriteThrough)
    try { $stream.Write($bytes,0,$bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
Save-ValidationReceipt
try {
    switch ($Task) {
        'Frozen' {
            $env:MORICE_BUNDLE_MODELS='0'
            $taskRecord['artifact_directory'] = Join-Path $taskBuild "$RunName-frozen"
            & $taskPython -m PyInstaller --noconfirm --workpath build/phase10-dist-work --distpath $taskRecord.artifact_directory MORICE.spec *> $taskLog
        }
        'Regression' { & $taskPython scripts/run_isolated_tests.py -q -o faulthandler_timeout=120 *> $taskLog }
        'Wheel' {
            $taskRecord['artifact_directory'] = Join-Path $taskBuild "$RunName-wheel"
            & $taskPython -m pip wheel . --no-deps --no-build-isolation --wheel-dir $taskRecord.artifact_directory *> $taskLog
        }
    }
    $taskRecord['exit_code'] = $LASTEXITCODE
    $taskRecord.status = if ($LASTEXITCODE -eq 0) { 'COMPLETED' } else { 'FAILED' }
} catch {
    $taskRecord.status = 'FAILED'; $taskRecord['error'] = $_.Exception.Message
    $taskRecord['exit_code'] = 1
} finally {
    $taskRecord['finished_utc'] = [DateTime]::UtcNow.ToString('o')
    Save-ValidationReceipt
}
exit $taskRecord.exit_code

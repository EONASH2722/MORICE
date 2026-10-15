param(
    [Parameter(Mandatory=$true)][string]$Candidate,
    [Parameter(Mandatory=$true)][string]$Parity,
    [Parameter(Mandatory=$true)][string]$Startup,
    [Parameter(Mandatory=$true)][string]$Regression,
    [Parameter(Mandatory=$true)][string]$RegressionReceipt
)
$ErrorActionPreference = 'Stop'
$taskWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
function Assert-WorkspacePath([string]$target) {
    $absolute = [IO.Path]::GetFullPath($target)
    if (-not $absolute.StartsWith($taskWorkspace + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Target outside named workspace: $absolute" }
    return $absolute
}
$candidateDirectory = Assert-WorkspacePath (Resolve-Path -LiteralPath $Candidate).Path
$distRoot = Assert-WorkspacePath (Join-Path $taskWorkspace 'dist')
$installedDirectory = Assert-WorkspacePath (Join-Path $distRoot 'MORICE')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDirectory = Assert-WorkspacePath (Join-Path $taskWorkspace "build\phase10-dist-backups\$stamp")
$stagedDirectory = Assert-WorkspacePath (Join-Path $distRoot "MORICE.next-$stamp")
foreach ($directory in @($candidateDirectory,$distRoot,$installedDirectory)) {
    if ((Get-Item -LiteralPath $directory).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Preflight rejects a redirected directory: $directory" }
}
$parityRecord = Get-Content -LiteralPath $Parity -Raw | ConvertFrom-Json
$startupRecord = Get-Content -LiteralPath $Startup -Raw | ConvertFrom-Json
$regressionText = Get-Content -LiteralPath $Regression -Raw
$regressionRecord = Get-Content -LiteralPath $RegressionReceipt -Raw | ConvertFrom-Json
$taskSource = & (Join-Path $taskWorkspace '.venv\Scripts\python.exe') -c "import hashlib;from pathlib import Path;r=Path.cwd();h=hashlib.sha256();[(h.update(str(p.relative_to(r)).encode()),h.update(p.read_bytes())) for p in sorted((r/'morice').rglob('*.py'))];print(h.hexdigest())"
if ($LASTEXITCODE -ne 0 -or $taskSource.Trim() -ne $parityRecord.source_sha256) { throw 'Current source differs from the verified executable.' }
if ($regressionRecord.status -ne 'COMPLETED' -or $regressionRecord.exit_code -ne 0 -or $regressionRecord.source_sha256 -ne $parityRecord.source_sha256) { throw 'Final full regression receipt does not match the candidate.' }
$taskTestSource = & (Join-Path $taskWorkspace '.venv\Scripts\python.exe') -c "import hashlib;from pathlib import Path;r=Path.cwd();h=hashlib.sha256();[(h.update(str(p.relative_to(r)).encode()),h.update(p.read_bytes())) for p in sorted((r/'tests').rglob('*.py'))];print(h.hexdigest())"
if ($LASTEXITCODE -ne 0 -or $taskTestSource.Trim() -ne $regressionRecord.test_source_sha256) { throw 'Tests changed after the final regression started.' }
if ((Resolve-Path -LiteralPath $regressionRecord.log).Path -ne (Resolve-Path -LiteralPath $Regression).Path) { throw 'Regression receipt belongs to another log.' }
if ($startupRecord.validation_exe_sha256 -ne $parityRecord.exe_sha256 -or (Resolve-Path -LiteralPath $startupRecord.validation_executable).Path -ne (Join-Path $candidateDirectory 'MORICE.exe')) { throw 'Startup receipt belongs to another executable.' }
if ($parityRecord.status -ne 'FROZEN_ARCHIVE_PARITY_PASSED') { throw 'Archive parity has not passed.' }
if (-not $startupRecord.frozen -or -not $startupRecord.production_window_factory -or $startupRecord.window_class -ne 'RenovatedWindow' -or $startupRecord.critical_failures -ne 0 -or -not $startupRecord.shutdown.clean) { throw 'Production frozen startup has not passed.' }
if ($regressionText -notmatch '(?m)^\d+ passed, \d+ subtests passed in ' -or $regressionText -match '(?m)^FAILED ') { throw 'Clean full regression is required.' }
if ((Resolve-Path -LiteralPath $parityRecord.directory).Path -ne $candidateDirectory) { throw 'Parity belongs to another candidate.' }
if ((Get-FileHash -LiteralPath (Join-Path $candidateDirectory 'MORICE.exe')).Hash.ToLowerInvariant() -ne $parityRecord.exe_sha256) { throw 'Candidate executable changed.' }
if (Get-Process -Name MORICE -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($distRoot + '\', [StringComparison]::OrdinalIgnoreCase) }) { throw 'Installed MORICE is running; preserve its work before replacing it.' }
$rootExecutable = Assert-WorkspacePath (Join-Path $distRoot 'MORICE.exe')
$rootInternal = Assert-WorkspacePath (Join-Path $distRoot '_internal')
$reuseInternalJunction=$false
if (Test-Path -LiteralPath $rootInternal) {
    $rootInternalItem=Get-Item -LiteralPath $rootInternal
    $expectedTarget=Assert-WorkspacePath (Join-Path $installedDirectory '_internal')
    if ($rootInternalItem.LinkType -ne 'Junction' -or @($rootInternalItem.Target).Count -ne 1 -or [IO.Path]::GetFullPath([string](@($rootInternalItem.Target)[0])) -ne $expectedTarget) { throw 'Root _internal is not the known installed-app junction.' }
    $reuseInternalJunction=$true
}
Copy-Item -LiteralPath $candidateDirectory -Destination $stagedDirectory -Recurse
$sourceFiles = @(Get-ChildItem -LiteralPath $candidateDirectory -Recurse -File)
$stagedFiles = @(Get-ChildItem -LiteralPath $stagedDirectory -Recurse -File)
if ($sourceFiles.Count -ne $stagedFiles.Count -or (Get-FileHash -LiteralPath (Join-Path $stagedDirectory 'MORICE.exe')).Hash.ToLowerInvariant() -ne $parityRecord.exe_sha256) { throw 'Staged copy does not match the verified candidate.' }
foreach ($sourceFile in $sourceFiles) {
    $relative = $sourceFile.FullName.Substring(($candidateDirectory + '\').Length)
    $copiedFile = Assert-WorkspacePath (Join-Path $stagedDirectory $relative)
    if ((Get-FileHash -LiteralPath $sourceFile.FullName).Hash -ne (Get-FileHash -LiteralPath $copiedFile).Hash) { throw "Staged file differs: $relative" }
}
$preservedModels = @()
foreach ($model in Get-ChildItem -LiteralPath $installedDirectory -Recurse -File -Filter '*.gguf') {
    $relative = $model.FullName.Substring(($installedDirectory + '\').Length)
    $destination = Assert-WorkspacePath (Join-Path $stagedDirectory $relative)
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    New-Item -ItemType HardLink -Path $destination -Target $model.FullName | Out-Null
    if ((Get-Item -LiteralPath $destination).Length -ne $model.Length) { throw 'Existing model preservation failed.' }
    $preservedModels += [pscustomobject]@{ relative=$relative; bytes=$model.Length; method='Same-volume hard link; original bytes retained' }
}
New-Item -ItemType Directory -Path $backupDirectory | Out-Null
$previousDirectory = Assert-WorkspacePath (Join-Path $backupDirectory 'MORICE')
Move-Item -LiteralPath $installedDirectory -Destination $previousDirectory
try { Move-Item -LiteralPath $stagedDirectory -Destination $installedDirectory }
catch { Move-Item -LiteralPath $previousDirectory -Destination $installedDirectory; throw }
if (Test-Path -LiteralPath $rootExecutable) { Move-Item -LiteralPath $rootExecutable -Destination (Join-Path $backupDirectory 'MORICE-standalone.exe') }
New-Item -ItemType HardLink -Path $rootExecutable -Target (Join-Path $installedDirectory 'MORICE.exe') | Out-Null
if (-not $reuseInternalJunction) { New-Item -ItemType Junction -Path $rootInternal -Target (Join-Path $installedDirectory '_internal') | Out-Null }
$receipt = [ordered]@{
    status='LOCAL_DIST_UPDATED'; installed=$installedDirectory; root_executable=$rootExecutable;
    backup=$backupDirectory; exe_sha256=$parityRecord.exe_sha256; source_sha256=$parityRecord.source_sha256;
    existing_local_models_retained=$preservedModels; release_candidate_contains_gguf=$false;
    public_actions_taken=$false;
    release_packaging_source=$candidateDirectory;
    note='Local install retains preexisting weights. Public packaging must use the verified model-free candidate, not this private local installation.'
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskWorkspace 'build\phase10-dist-update.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 6

param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$SkipPortable
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Release = Join-Path $Root "release"
$Dist = Join-Path $Root "dist\MORICE"
$BuildDataRoot = if ($env:MORICE_LOCAL_DATA_DIR) {
    $env:MORICE_LOCAL_DATA_DIR
}
else {
    Join-Path ([System.IO.Path]::GetPathRoot($Root)) "MORICE_DATA"
}
$BuildTemp = Join-Path $BuildDataRoot "Temp"
$PyInstallerConfig = Join-Path $BuildDataRoot "PyInstaller"
New-Item -ItemType Directory -Force -Path $BuildTemp, $PyInstallerConfig | Out-Null
$env:TEMP = $BuildTemp
$env:TMP = $BuildTemp
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerConfig
$Version = (& python -c "from morice.version import VERSION; print(VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $Version) {
    throw "Unable to read the authoritative MORICE version."
}
$TagVersion = "v$Version"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not $SkipTests) {
    Push-Location $Root
    try {
        Invoke-Checked "Version consistency" {
            python (Join-Path $PSScriptRoot "validate_version.py") --root $Root
        }
        Invoke-Checked "Python tests" {
            python -m unittest discover -s tests
        }
        Push-Location (Join-Path $Root "vnext")
        try {
            $PackageManager = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
            if ($null -eq $PackageManager) {
                $PackageManager = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
            }
            if ($null -eq $PackageManager) {
                throw "Install pnpm or npm to run the VNext release checks."
            }
            Invoke-Checked "VNext tests" {
                & $PackageManager.Source test
            }
            Invoke-Checked "VNext typecheck" {
                & $PackageManager.Source run typecheck
            }
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $Release | Out-Null
$ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
$ResolvedRelease = (Resolve-Path -LiteralPath $Release).Path
if (-not $ResolvedRelease.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Release directory resolved outside the MORICE workspace."
}
Get-ChildItem -LiteralPath $Release -Force | Remove-Item -Recurse -Force

Push-Location $Root
try {
    Invoke-Checked "PyInstaller build" {
        python -m PyInstaller --noconfirm --clean MORICE.spec
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $Dist "MORICE.exe"))) {
    throw "PyInstaller did not produce dist\MORICE\MORICE.exe."
}

if (-not $SkipPortable) {
    $Portable = Join-Path $Release "MORICE-Portable-$TagVersion-Windows-x64.zip"
    Invoke-Checked "Portable package build" {
        & python (Join-Path $PSScriptRoot "package_portable.py") `
            --source $Dist `
            --output $Portable
    }
    Invoke-Checked "Portable release split" {
        & python (Join-Path $PSScriptRoot "split_release_asset.py") `
            --source $Portable `
            --output-dir $Release `
            --part-size 1900000000
    }
    Copy-Item `
        -LiteralPath (Join-Path $Root "installer\MORICE-Portable-Reassemble.ps1") `
        -Destination (Join-Path $Release "MORICE-Portable-$TagVersion-Windows-x64-reassemble.ps1") `
        -Force
    Remove-Item -LiteralPath $Portable -Force
}

$DocsBundle = Join-Path $Release "MORICE-$TagVersion-Documentation.zip"
Invoke-Checked "Documentation package build" {
    & python (Join-Path $PSScriptRoot "package_docs.py") `
        --root $Root `
        --output $DocsBundle
}

$SourceBundle = Join-Path $Release "MORICE-$TagVersion-Source.zip"
Invoke-Checked "Source package build" {
    & python (Join-Path $PSScriptRoot "package_source.py") `
        --root $Root `
        --output $SourceBundle `
        --version $Version
}

Invoke-Checked "Python wheel and source distribution" {
    Push-Location $env:TEMP
    try {
        & python -m build --outdir $Release $Root
    }
    finally {
        Pop-Location
    }
}

$ReleaseNotes = Join-Path $Root "docs\release-notes-$Version.md"
if (-not (Test-Path -LiteralPath $ReleaseNotes)) {
    throw "Release notes are missing: $ReleaseNotes"
}
Copy-Item `
    -LiteralPath $ReleaseNotes `
    -Destination (Join-Path $Release "MORICE-$TagVersion-Release-Notes.md") `
    -Force

if (-not $SkipInstaller) {
    $Compiler = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    $CompilerPath = if ($null -ne $Compiler) { $Compiler.Source } else { $null }
    if (-not $CompilerPath) {
        $CompilerCandidates = @()
        if ($env:LOCALAPPDATA) {
            $CompilerCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
        }
        if (${env:ProgramFiles(x86)}) {
            $CompilerCandidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        }
        if ($env:ProgramFiles) {
            $CompilerCandidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
        }
        $CompilerPath = $CompilerCandidates |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
    }
    if (-not $CompilerPath) {
        throw "Inno Setup 6 is required to compile installer\MORICE.iss."
    }
    Invoke-Checked "Installer build" {
        & $CompilerPath "/DMyAppVersion=$Version" (Join-Path $Root "installer\MORICE.iss")
    }
}

$Report = Join-Path $Release "MORICE-$TagVersion-Package-Contents.json"
Invoke-Checked "Release content audit" {
    & python (Join-Path $PSScriptRoot "audit_release.py") `
        --release $Release `
        --version $Version `
        --report $Report
}

Get-ChildItem -LiteralPath $Release -File |
Where-Object { $_.Name -notin @("checksums.json", "SHA256SUMS.txt") } |
ForEach-Object {
    $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
    [PSCustomObject]@{
        Name = $_.Name
        Bytes = $_.Length
        SHA256 = $Hash.Hash.ToLowerInvariant()
    }
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Release "checksums.json") -Encoding UTF8

$ChecksumManifest = Get-Content -LiteralPath (Join-Path $Release "checksums.json") -Raw |
    ConvertFrom-Json
@($ChecksumManifest) | ForEach-Object {
    "{0}  {1}" -f $_.SHA256, $_.Name
} | Set-Content -LiteralPath (Join-Path $Release "SHA256SUMS.txt") -Encoding ascii

Invoke-Checked "Release checksum verification" {
    & python (Join-Path $PSScriptRoot "audit_release.py") `
        --release $Release `
        --version $Version `
        --verify-checksums
}

Write-Host "MORICE release artifacts are ready in $Release"

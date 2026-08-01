param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$SkipPortable
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Release = Join-Path $Root "release"
$Dist = Join-Path $Root "dist\MORICE"

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
Get-ChildItem -LiteralPath $Release -File |
Where-Object {
    $_.Name -like "MORICE-*" -or $_.Name -eq "checksums.json"
} |
Remove-Item -Force

Push-Location $Root
try {
    Invoke-Checked "PyInstaller build" {
        python -m PyInstaller --noconfirm MORICE.spec
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $Dist "MORICE.exe"))) {
    throw "PyInstaller did not produce dist\MORICE\MORICE.exe."
}

if (-not $SkipPortable) {
    $Portable = Join-Path $Release "MORICE-0.7.0-vnext-portable.zip"
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
        -Destination (Join-Path $Release "MORICE-0.7.0-vnext-portable-reassemble.ps1") `
        -Force
    Remove-Item -LiteralPath $Portable -Force
}

$DocsBundle = Join-Path $Release "MORICE-0.7.0-vnext-documentation.zip"
Invoke-Checked "Documentation package build" {
    & python (Join-Path $PSScriptRoot "package_docs.py") `
        --root $Root `
        --output $DocsBundle
}

$SourceBundle = Join-Path $Release "MORICE-0.7.0-vnext-source.zip"
Invoke-Checked "Source package build" {
    & python (Join-Path $PSScriptRoot "package_source.py") `
        --root $Root `
        --output $SourceBundle
}

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
        & $CompilerPath (Join-Path $Root "installer\MORICE.iss")
    }
}

Get-ChildItem -LiteralPath $Release -File |
Where-Object { $_.Name -ne "checksums.json" } |
ForEach-Object {
    $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
    [PSCustomObject]@{
        Name = $_.Name
        Bytes = $_.Length
        SHA256 = $Hash.Hash.ToLowerInvariant()
    }
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Release "checksums.json") -Encoding UTF8

Write-Host "MORICE release artifacts are ready in $Release"

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

New-Item -ItemType Directory -Force -Path $Release | Out-Null

if (-not $SkipPortable) {
    $Portable = Join-Path $Release "MORICE-0.7.0-vnext-portable.zip"
    Invoke-Checked "Portable package build" {
        & python (Join-Path $PSScriptRoot "package_portable.py") `
            --source $Dist `
            --output $Portable
    }
}

if (-not $SkipInstaller) {
    $Compiler = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($null -eq $Compiler) {
        throw "Inno Setup 6 is required to compile installer\MORICE.iss."
    }
    Invoke-Checked "Installer build" {
        & $Compiler.Source (Join-Path $Root "installer\MORICE.iss")
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

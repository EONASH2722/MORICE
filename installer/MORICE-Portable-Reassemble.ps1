param(
    [string]$ManifestPath = ""
)

$ErrorActionPreference = "Stop"
if (-not $ManifestPath) {
    $ManifestPath = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "MORICE-Portable-*.zip.parts.json" |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ManifestPath -or -not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Keep this script beside the portable parts manifest and all numbered parts."
}

$ManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$Manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$Output = Join-Path (Split-Path -Parent $ManifestPath) $Manifest.output
$Temporary = "$Output.partial"

if (Test-Path -LiteralPath $Temporary) {
    Remove-Item -LiteralPath $Temporary -Force
}

$Destination = [System.IO.File]::Open(
    $Temporary,
    [System.IO.FileMode]::CreateNew,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
)
try {
    foreach ($Part in $Manifest.parts) {
        $PartPath = Join-Path (Split-Path -Parent $ManifestPath) $Part.name
        if (-not (Test-Path -LiteralPath $PartPath)) {
            throw "Missing portable part: $($Part.name)"
        }
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PartPath).Hash.ToLowerInvariant()
        if ($Hash -ne $Part.sha256) {
            throw "Checksum mismatch for portable part: $($Part.name)"
        }
        $Source = [System.IO.File]::OpenRead($PartPath)
        try {
            $Source.CopyTo($Destination)
        }
        finally {
            $Source.Dispose()
        }
    }
}
finally {
    $Destination.Dispose()
}

$OutputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Temporary).Hash.ToLowerInvariant()
if ($OutputHash -ne $Manifest.sha256) {
    Remove-Item -LiteralPath $Temporary -Force
    throw "The reconstructed portable ZIP failed its checksum."
}
Move-Item -LiteralPath $Temporary -Destination $Output -Force
Write-Host "Portable ZIP ready: $Output"

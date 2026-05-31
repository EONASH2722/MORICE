param(
    [string]$AppDir = "",
    [string]$OutDir = "",
    [long]$ChunkSizeBytes = 1992294400,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $AppDir.Trim()) {
    $AppDir = Join-Path $RepoRoot "dist\MORICE"
}
if (-not $OutDir.Trim()) {
    $OutDir = Join-Path $RepoRoot "release\morice-pc-app"
}

$AppDir = [System.IO.Path]::GetFullPath($AppDir)
$OutDir = [System.IO.Path]::GetFullPath($OutDir)
$zipPath = Join-Path $OutDir "MORICE-PC.zip"

if (-not (Test-Path -LiteralPath $AppDir)) {
    throw "Packaged app folder not found: $AppDir. Run py -3.12 -m PyInstaller -y MORICE.spec first."
}
if ((Test-Path -LiteralPath $OutDir) -and -not $Force) {
    $existing = Get-ChildItem -LiteralPath $OutDir -Force -ErrorAction SilentlyContinue
    if ($existing) {
        throw "Output folder already has files. Re-run with -Force or choose a new -OutDir."
    }
}

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
if ($Force) {
    Get-ChildItem -LiteralPath $OutDir -Force | Remove-Item -Force
}

Write-Host "Creating MORICE-PC.zip"
$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if ($tar) {
    & tar.exe -a -cf $zipPath -C (Split-Path -Parent $AppDir) (Split-Path -Leaf $AppDir)
    if ($LASTEXITCODE -ne 0) {
        throw "tar.exe failed to create the ZIP package."
    }
}
else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($AppDir, $zipPath)
}

$zip = Get-Item -LiteralPath $zipPath
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToUpperInvariant()
$parts = New-Object System.Collections.Generic.List[string]
$partSizes = New-Object System.Collections.Generic.List[long]
$buffer = New-Object byte[] (8MB)
$inStream = [System.IO.File]::OpenRead($zipPath)
try {
    $partIndex = 1
    while ($inStream.Position -lt $inStream.Length) {
        $partName = "MORICE-PC.zip.part{0:D3}" -f $partIndex
        $partPath = Join-Path $OutDir $partName
        $remainingForPart = [Math]::Min($ChunkSizeBytes, $inStream.Length - $inStream.Position)
        $written = 0L
        Write-Host "Writing $partName"
        $outStream = [System.IO.File]::Open($partPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        try {
            while ($written -lt $remainingForPart) {
                $toRead = [Math]::Min($buffer.Length, $remainingForPart - $written)
                $read = $inStream.Read($buffer, 0, [int]$toRead)
                if ($read -le 0) {
                    break
                }
                $outStream.Write($buffer, 0, $read)
                $written += $read
            }
        }
        finally {
            $outStream.Dispose()
        }
        $parts.Add($partName)
        $partSizes.Add($written)
        $partIndex += 1
    }
}
finally {
    $inStream.Dispose()
}

$manifest = [ordered]@{
    packageFile = "MORICE-PC.zip"
    sha256 = $hash
    size = [long]$zip.Length
    chunkSizeBytes = [long]$ChunkSizeBytes
    parts = $parts.ToArray()
    partSizes = $partSizes.ToArray()
}

$manifestPath = Join-Path $OutDir "pc-app-manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "PC release files are ready in: $OutDir"
Write-Host "Upload the manifest and .part files to a GitHub release."

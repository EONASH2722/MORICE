param(
    [string]$ModelPath = "",
    [string]$OutDir = "",
    [long]$ChunkSizeBytes = 1992294400,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $ModelPath.Trim()) {
    $ModelPath = Join-Path $RepoRoot "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"
}
if (-not $OutDir.Trim()) {
    $OutDir = Join-Path $RepoRoot "release\model-hermes-3-llama-3.1-8b-q4-k-m"
}

$ModelPath = [System.IO.Path]::GetFullPath($ModelPath)
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

if (-not (Test-Path -LiteralPath $ModelPath)) {
    throw "Model file not found: $ModelPath"
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

$source = Get-Item -LiteralPath $ModelPath
$modelFile = $source.Name
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ModelPath).Hash.ToUpperInvariant()
$parts = New-Object System.Collections.Generic.List[string]
$partSizes = New-Object System.Collections.Generic.List[long]

$buffer = New-Object byte[] (8MB)
$inStream = [System.IO.File]::OpenRead($ModelPath)
try {
    $partIndex = 1
    while ($inStream.Position -lt $inStream.Length) {
        $partName = "{0}.part{1:D3}" -f $modelFile, $partIndex
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
    modelFile = $modelFile
    sha256 = $hash
    size = [long]$source.Length
    chunkSizeBytes = [long]$ChunkSizeBytes
    parts = $parts.ToArray()
    partSizes = $partSizes.ToArray()
}

$manifestPath = Join-Path $OutDir "model-manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "Model release files are ready in: $OutDir"
Write-Host "Upload every file in that folder to the GitHub release:"
Write-Host "https://github.com/EONASH2722/MORICE/releases/tag/model-hermes-3-llama-3.1-8b-q4-k-m"

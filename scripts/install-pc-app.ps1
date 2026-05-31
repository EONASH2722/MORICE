param(
    [string]$ReleaseBaseUrl = "https://github.com/EONASH2722/MORICE/releases/download/morice-pc-app",
    [string]$Destination = "",
    [switch]$SkipHashCheck
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if (-not $Destination.Trim()) {
    $Destination = Join-Path $env:USERPROFILE "MORICE"
}
$Destination = [System.IO.Path]::GetFullPath($Destination)

function Download-File($Url, $OutFile) {
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Join-Parts($PartPaths, $OutputPath) {
    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }
    $outStream = [System.IO.File]::Open($OutputPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        $buffer = New-Object byte[] (8MB)
        foreach ($partPath in $PartPaths) {
            Write-Host "Adding $(Split-Path -Leaf $partPath)"
            $inStream = [System.IO.File]::OpenRead($partPath)
            try {
                while (($read = $inStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $outStream.Write($buffer, 0, $read)
                }
            }
            finally {
                $inStream.Dispose()
            }
        }
    }
    finally {
        $outStream.Dispose()
    }
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("morice-pc-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $manifestPath = Join-Path $tempDir "pc-app-manifest.json"
    Download-File "$ReleaseBaseUrl/pc-app-manifest.json" $manifestPath
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $parts = @($manifest.parts)
    if (-not $parts.Count) {
        throw "PC app manifest has no package parts."
    }
    $partPaths = @()
    foreach ($part in $parts) {
        $partName = [string]$part
        $partPath = Join-Path $tempDir $partName
        Download-File "$ReleaseBaseUrl/$partName" $partPath
        $partPaths += $partPath
    }
    $zipPath = Join-Path $tempDir $manifest.packageFile
    Join-Parts $partPaths $zipPath
    $zip = Get-Item -LiteralPath $zipPath
    if ($zip.Length -ne [long]$manifest.size) {
        throw "Downloaded PC package size mismatch."
    }
    if (-not $SkipHashCheck) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToUpperInvariant()
        if ($hash -ne ([string]$manifest.sha256).ToUpperInvariant()) {
            throw "Downloaded PC package SHA256 mismatch."
        }
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $Destination -Force
    Write-Host "MORICE installed to: $Destination"
    Write-Host "Run: $Destination\MORICE\MORICE.exe"
}
finally {
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}

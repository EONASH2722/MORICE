param(
    [ValidateSet("auto", "github", "huggingface")]
    [string]$Source = "auto",
    [string]$ReleaseBaseUrl = "https://github.com/EONASH2722/MORICE/releases/download/model-hermes-3-llama-3.1-8b-q4-k-m",
    [string]$Destination = "",
    [switch]$SkipHashCheck
)

$ErrorActionPreference = "Stop"

$ModelFile = "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf"
$ExpectedSha256 = "D4403CE5A6E930F4C2509456388C20D633A15FF08DD52EF3B142FF1810EC3553"
$ExpectedSize = 4920733824
$HuggingFaceUrl = "https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B-GGUF/resolve/main/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf?download=true"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination.Trim()) {
    $Destination = Join-Path $RepoRoot $ModelFile
}
$Destination = [System.IO.Path]::GetFullPath($Destination)
$DestinationDir = Split-Path -Parent $Destination

function Get-ModelHash($Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Test-ExistingModel($Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne $ExpectedSize) {
        return $false
    }
    if ($SkipHashCheck) {
        return $true
    }
    return (Get-ModelHash $Path) -eq $ExpectedSha256
}

function Download-File($Url, $OutFile) {
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Join-Parts($PartPaths, $OutputPath) {
    $partial = "$OutputPath.partial"
    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial -Force
    }
    $outStream = [System.IO.File]::Open($partial, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
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
    Move-Item -LiteralPath $partial -Destination $OutputPath -Force
}

function Install-FromGitHubRelease($TempDir) {
    $manifestPath = Join-Path $TempDir "model-manifest.json"
    $manifestUrl = "$ReleaseBaseUrl/model-manifest.json"
    Download-File $manifestUrl $manifestPath
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $parts = @($manifest.parts)
    if (-not $parts.Count) {
        throw "GitHub model manifest has no parts."
    }
    $partPaths = @()
    foreach ($part in $parts) {
        $partName = [string]$part
        $partPath = Join-Path $TempDir $partName
        Download-File "$ReleaseBaseUrl/$partName" $partPath
        $partPaths += $partPath
    }
    Join-Parts $partPaths $Destination
}

function Install-Direct($Url, $TempDir) {
    $downloadPath = Join-Path $TempDir $ModelFile
    Download-File $Url $downloadPath
    Move-Item -LiteralPath $downloadPath -Destination $Destination -Force
}

New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null

if (Test-ExistingModel $Destination) {
    Write-Host "MORICE model is already installed: $Destination"
    exit 0
}

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("morice-model-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $installed = $false
    if ($Source -in @("auto", "github")) {
        try {
            Install-FromGitHubRelease $tempDir
            $installed = $true
        }
        catch {
            if ($Source -eq "github") {
                throw
            }
            Write-Host "GitHub release model was not available yet. Falling back to Hugging Face."
        }
    }
    if (-not $installed -and $Source -in @("auto", "huggingface")) {
        Install-Direct $HuggingFaceUrl $tempDir
        $installed = $true
    }
    if (-not $installed) {
        throw "No model source installed the file."
    }
    $item = Get-Item -LiteralPath $Destination
    if ($item.Length -ne $ExpectedSize) {
        throw "Downloaded model size mismatch. Expected $ExpectedSize bytes, got $($item.Length)."
    }
    if (-not $SkipHashCheck) {
        $hash = Get-ModelHash $Destination
        if ($hash -ne $ExpectedSha256) {
            throw "Downloaded model SHA256 mismatch. Expected $ExpectedSha256, got $hash."
        }
    }
    Write-Host "MORICE model installed: $Destination"
}
finally {
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}

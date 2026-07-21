param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = "D:\oppw"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceCandidate = Join-Path $packageRoot "mt5\oppw_mt5_continuous_v50.py"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw "RepoRoot cannot be empty."
}

$resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).ProviderPath
$source = (Resolve-Path -LiteralPath $sourceCandidate -ErrorAction Stop).ProviderPath
$targets = @(
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous_v50.py"),
    (Join-Path $resolvedRoot "mt5\demo\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\demo\oppw_mt5_continuous_v50.py"),
    (Join-Path $resolvedRoot "mt5\real\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\real\oppw_mt5_continuous_v50.py")
)

foreach ($target in $targets) {
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        continue
    }

    if ([string]::Equals($source, $target, [System.StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Already installed $target"
        continue
    }

    Copy-Item -LiteralPath $source -Destination $target -Force
    Write-Host "Installed $target"
}

$expectedHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        continue
    }
    $actualHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "Installed file hash mismatch: $target"
    }
}

Write-Host "OPPW MT5 v50 installed and verified."
Write-Host "Private configs, state, logs, and credentials were not overwritten."
Write-Host "Restart PUBLISHER first, then EXECUTOR."

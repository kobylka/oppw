param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = "D:\oppw"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $packageRoot "mt5\oppw_mt5_continuous_v48_6.py"
$resolvedRoot = [System.IO.Path]::GetFullPath($RepoRoot)

if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing package source: $source"
}
if (-not (Test-Path -LiteralPath $resolvedRoot -PathType Container)) {
    throw "Repository root does not exist: $resolvedRoot"
}

$targets = @(
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous_v48.py"),
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous_v48_6.py"),
    (Join-Path $resolvedRoot "mt5\demo\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\real\oppw_mt5_continuous.py")
)

foreach ($target in $targets) {
    $parent = Split-Path -Parent $target
    if (Test-Path -LiteralPath $parent -PathType Container) {
        Copy-Item -LiteralPath $source -Destination $target -Force
        Write-Host "Installed $target"
    }
}

Write-Host "OPPW MT5 v48.6 installed. Private configs were not changed."

param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = "D:\oppw"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $packageRoot "mt5\oppw_mt5_continuous_v48_7.py"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw "RepoRoot cannot be empty."
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository root does not exist: $RepoRoot"
}
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Missing package source: $source"
}

$resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$targets = @(
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous.py"),
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous_v48.py"),
    (Join-Path $resolvedRoot "mt5\oppw_mt5_continuous_v48_7.py"),
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

Write-Host "OPPW MT5 v48.7 installed. Private configs were not changed."
Write-Host "Install android\OPPW-Monitor-v14.3-debug.apk to update the Position wording."

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = 'D:\oppw'
)

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSCommandPath
$resolvedRepo = [System.IO.Path]::GetFullPath($RepoRoot.Trim().TrimEnd('\', '/'))
if (-not (Test-Path -LiteralPath $resolvedRepo -PathType Container)) {
    throw "Repository root does not exist: $resolvedRepo"
}

function Copy-PackageFile {
    param([string]$RelativeSource, [string]$RelativeDestination)
    $source = Join-Path $packageRoot $RelativeSource
    $destination = Join-Path $resolvedRepo $RelativeDestination
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Package file is missing: $source"
    }
    $destinationDirectory = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $destinationDirectory)) {
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    }
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Write-Host "Installed $RelativeDestination"
}

$loopTargets = @(
    'mt5\oppw_mt5_continuous.py',
    'mt5\oppw_mt5_continuous_v51.py',
    'mt5\demo\oppw_mt5_continuous.py',
    'mt5\demo\oppw_mt5_continuous_v51.py',
    'mt5\real\oppw_mt5_continuous.py',
    'mt5\real\oppw_mt5_continuous_v51.py'
)
foreach ($target in $loopTargets) {
    Copy-PackageFile 'mt5\oppw_mt5_continuous_v51.py' $target
}

Copy-PackageFile 'mt5\oppw_mt5_config.example.py' 'mt5\oppw_mt5_config.example.py'
Copy-PackageFile 'mt5\demo\oppw_mt5_config.example.py' 'mt5\demo\oppw_mt5_config.example.py'
Copy-PackageFile 'mt5\real\oppw_mt5_config.example.py' 'mt5\real\oppw_mt5_config.example.py'
Copy-PackageFile 'mt5\tests\test_strategy_authority_v51.py' 'mt5\tests\test_strategy_authority_v51.py'
Copy-PackageFile 'docs\OPPW24_STRATEGY_SPECIFICATION_v51.md' 'docs\OPPW24_STRATEGY_SPECIFICATION_v51.md'

$backendFiles = @(
    'authority.php', 'ingest.php', 'events-ingest.php', 'cashflow.php',
    'trade-admin.php', 'mobile-receipt.php', 'strategy-decisions.php',
    'strategy-specifications.php', 'analytics.php'
)
foreach ($file in $backendFiles) {
    Copy-PackageFile ("Mobile\backend\$file") ("Mobile\backend\$file")
}
Copy-PackageFile 'Mobile\backend\sql\migrate_v51_strategy_authority.sql' 'Mobile\backend\sql\migrate_v51_strategy_authority.sql'

$installedLoop = Join-Path $resolvedRepo 'mt5\oppw_mt5_continuous.py'
$buildLine = Select-String -LiteralPath $installedLoop -Pattern 'canonical-spec-immutable-authority-v51' -SimpleMatch
if (-not $buildLine) { throw 'Installed loop does not contain the v51 build ID.' }

Write-Host ''
Write-Host 'v51 files installed. Private configuration was not changed.'
Write-Host 'Run the SQL migration and upload the backend files before restarting PUBLISHER and EXECUTOR.'


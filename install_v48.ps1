param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = "D:\oppw",

    [Parameter(Mandatory = $false)]
    [string]$SourceRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = Split-Path -Parent $PSCommandPath
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "Repository root does not exist: $RepoRoot"
}
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    throw "Package source root does not exist: $SourceRoot"
}
$repo = (Resolve-Path -LiteralPath $RepoRoot).Path
$source = (Resolve-Path -LiteralPath $SourceRoot).Path

$loopSource = Join-Path $source "mt5\oppw_mt5_continuous_v48.py"
if (-not (Test-Path -LiteralPath $loopSource -PathType Leaf)) {
    throw "v48.2 source not found: $loopSource"
}

$copies = @(
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\oppw_mt5_continuous_v48.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\oppw_mt5_continuous_v48_1.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\oppw_mt5_continuous_v48_2.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\oppw_mt5_continuous.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\demo\oppw_mt5_continuous_v48.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\demo\oppw_mt5_continuous_v48_1.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\demo\oppw_mt5_continuous_v48_2.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\demo\oppw_mt5_continuous.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\real\oppw_mt5_continuous_v48.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\real\oppw_mt5_continuous_v48_1.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\real\oppw_mt5_continuous_v48_2.py") },
    @{ Source = $loopSource; Target = (Join-Path $repo "mt5\real\oppw_mt5_continuous.py") },
    @{ Source = (Join-Path $source "mt5\oppw_mt5_config.example.py"); Target = (Join-Path $repo "mt5\oppw_mt5_config.example.py") },
    @{ Source = (Join-Path $source "mt5\demo\oppw_mt5_config.example.py"); Target = (Join-Path $repo "mt5\demo\oppw_mt5_config.example.py") },
    @{ Source = (Join-Path $source "mt5\real\oppw_mt5_config.example.py"); Target = (Join-Path $repo "mt5\real\oppw_mt5_config.example.py") },
    @{ Source = (Join-Path $source "Mobile\backend\lib.php"); Target = (Join-Path $repo "Mobile\backend\lib.php") },
    @{ Source = (Join-Path $source "Mobile\backend\ingest.php"); Target = (Join-Path $repo "Mobile\backend\ingest.php") },
    @{ Source = (Join-Path $source "Mobile\backend\coordination.php"); Target = (Join-Path $repo "Mobile\backend\coordination.php") },
    @{ Source = (Join-Path $source "Mobile\backend\events-ingest.php"); Target = (Join-Path $repo "Mobile\backend\events-ingest.php") },
    @{ Source = (Join-Path $source "Mobile\backend\sql\migrate_v48_global_leases.sql"); Target = (Join-Path $repo "Mobile\backend\sql\migrate_v48_global_leases.sql") }
)

foreach ($item in $copies) {
    if (-not (Test-Path -LiteralPath $item.Source -PathType Leaf)) {
        throw "Required package file is missing: $($item.Source)"
    }
    $targetDirectory = Split-Path -Parent $item.Target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $item.Source -Destination $item.Target -Force
}

# Old coordination files are not used by v48. Preserve them for audit instead
# of deleting them. Private configs and strategy state files are never moved.
$mt5Root = [System.IO.Path]::GetFullPath((Join-Path $repo "mt5"))
$archive = Join-Path $mt5Root ("legacy-v47-coordination-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$legacyFiles = Get-ChildItem -LiteralPath $mt5Root -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -like "oppw_mt5*.lock" -or
        $_.Name -like "oppw_mt5*.publisher.heartbeat.json" -or
        $_.Name -like "oppw_monitor_equity_history*.events.jsonl" -or
        $_.Name -like "oppw_monitor_equity_history*.events.jsonl.lock"
    }

foreach ($legacy in $legacyFiles) {
    $resolved = [System.IO.Path]::GetFullPath($legacy.FullName)
    if (-not $resolved.StartsWith($mt5Root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to move a path outside the MT5 workspace: $resolved"
    }
    New-Item -ItemType Directory -Path $archive -Force | Out-Null
    $relative = $resolved.Substring($mt5Root.Length).TrimStart(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $safeName = $relative.Replace([System.IO.Path]::DirectorySeparatorChar, "__")
    Move-Item -LiteralPath $resolved -Destination (Join-Path $archive $safeName) -Force
}

Write-Host "v48.2 source and backend files installed in $repo"
Write-Host "Private account configs were not overwritten. Merge the new v48 coordination fields manually."
Write-Host "Run the SQL migration before starting either process:"
Write-Host "  Mobile\backend\sql\migrate_v48_global_leases.sql"
Write-Host "Upload lib.php, ingest.php, coordination.php, and events-ingest.php to the backend."
Write-Host "Start PUBLISHER first, then EXECUTOR."

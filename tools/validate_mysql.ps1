[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Image = 'mysql:8.4'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
$sqlRoot = Join-Path $root 'Mobile\backend\sql'
$orderFile = Join-Path $sqlRoot 'migration-order.txt'
if (-not (Test-Path -LiteralPath $orderFile -PathType Leaf)) {
    throw "Migration order file is missing: $orderFile"
}

$docker = Get-Command docker -ErrorAction Stop
$dockerConfig = Join-Path ([IO.Path]::GetTempPath()) 'oppw-release-docker-config'
New-Item -ItemType Directory -Path $dockerConfig -Force | Out-Null
$previousDockerConfig = $env:DOCKER_CONFIG
$env:DOCKER_CONFIG = $dockerConfig
$container = 'oppw-mysql-validation-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$containerStarted = $false

try {
    & $docker.Source info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not available.' }

    & $docker.Source run --detach --rm --name $container `
        --env 'MYSQL_ALLOW_EMPTY_PASSWORD=yes' `
        --env 'MYSQL_DATABASE=oppw_monitor' $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start temporary MySQL container.' }
    $containerStarted = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $savedErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $schemaName = (& $docker.Source exec $container mysql -N -uroot `
                -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='oppw_monitor'" 2>$null)
            $schemaExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        if ($schemaExitCode -eq 0 -and ($schemaName -join '').Trim() -eq 'oppw_monitor') {
            $ready = $true
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Temporary MySQL/database initialization did not finish within 30 seconds.' }

    $migrations = Get-Content -LiteralPath $orderFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' -and -not $_.StartsWith('#') }
    foreach ($migration in $migrations) {
        $path = Join-Path $sqlRoot $migration
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Migration listed but missing: $migration"
        }
        Write-Host "Applying $migration"
        Get-Content -LiteralPath $path -Raw |
            & $docker.Source exec -i $container mysql -uroot --database=oppw_monitor
        if ($LASTEXITCODE -ne 0) { throw "MySQL rejected migration: $migration" }
    }

    $tableQuery = "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME IN ('strategy_specifications','strategy_account_spec_assignments','strategy_decisions','strategy_execution_stages','strategy_fills','strategy_protection_changes','strategy_trade_ledger','account_cash_flows');"
    $tableCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $tableQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$tableCount -ne 8) { throw "Authority-table validation failed: $tableCount/8" }

    $serviceTableQuery = "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME IN ('strategy_service_desired_state','strategy_supervisor_nodes','strategy_service_control_events');"
    $serviceTableCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $serviceTableQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$serviceTableCount -ne 3) { throw "Service-supervision table validation failed: $serviceTableCount/3" }

    $lifecycleTableQuery = "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME IN ('strategy_equity_daily','strategy_retention_runs');"
    $lifecycleTableCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $lifecycleTableQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$lifecycleTableCount -ne 2) { throw "Data-lifecycle table validation failed: $lifecycleTableCount/2" }

    $tradeClassColumnQuery = "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME='strategy_trades' AND COLUMN_NAME IN ('preleverage_return_percent','trade_class');"
    $tradeClassColumnCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $tradeClassColumnQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$tradeClassColumnCount -ne 2) { throw "Trade-class column validation failed: $tradeClassColumnCount/2" }

    $tradeClassTriggerQuery = "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='oppw_monitor' AND TRIGGER_NAME IN ('strategy_trades_class_before_insert','strategy_trades_class_before_update');"
    $tradeClassTriggerCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $tradeClassTriggerQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$tradeClassTriggerCount -ne 2) { throw "Trade-class trigger validation failed: $tradeClassTriggerCount/2" }

    $snapshotUniqueQuery = "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME='strategy_snapshots' AND INDEX_NAME='uq_snapshot_strategy' AND COLUMN_NAME='strategy_key' AND NON_UNIQUE=0;"
    $snapshotUniqueCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $snapshotUniqueQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$snapshotUniqueCount -ne 1) { throw "Current-snapshot uniqueness validation failed: $snapshotUniqueCount/1" }

    $triggerQuery = "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='oppw_monitor' AND TRIGGER_NAME REGEXP '_no_(update|delete)$';"
    $triggerCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $triggerQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$triggerCount -ne 19) { throw "Immutability-trigger validation failed: $triggerCount/19" }

    $marketRetentionTriggerQuery = "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='oppw_monitor' AND TRIGGER_NAME='strategy_market_points_no_delete' AND EVENT_MANIPULATION='DELETE';"
    $marketRetentionTriggerCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $marketRetentionTriggerQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$marketRetentionTriggerCount -ne 1) { throw "Market-minute retention trigger validation failed: $marketRetentionTriggerCount/1" }

    $retentionIndexQuery = "SELECT COUNT(DISTINCT INDEX_NAME) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='oppw_monitor' AND INDEX_NAME IN ('idx_event_retention_time','idx_equity_retention_time');"
    $retentionIndexCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $retentionIndexQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$retentionIndexCount -ne 2) { throw "Retention-index validation failed: $retentionIndexCount/2" }

    $marketForeignKeyQuery = "SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='oppw_monitor' AND TABLE_NAME='strategy_market_points' AND CONSTRAINT_NAME='fk_market_account' AND DELETE_RULE='RESTRICT';"
    $marketForeignKeyCount = (& $docker.Source exec $container `
        mysql -N -uroot --database=oppw_monitor -e $marketForeignKeyQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$marketForeignKeyCount -ne 1) { throw "Market-minute cascade protection validation failed: $marketForeignKeyCount/1" }

    Write-Host "MYSQL VALIDATION PASSED authority_tables=$tableCount service_tables=$serviceTableCount lifecycle_tables=$lifecycleTableCount trade_class_columns=$tradeClassColumnCount trade_class_triggers=$tradeClassTriggerCount snapshot_unique=$snapshotUniqueCount immutable_triggers=$triggerCount market_retention_trigger=$marketRetentionTriggerCount retention_indexes=$retentionIndexCount market_fk_restrict=$marketForeignKeyCount image=$Image"
} finally {
    if ($containerStarted) {
        try {
            & $docker.Source rm --force $container 2>$null | Out-Null
        } catch {
            Write-Warning "Could not remove temporary MySQL container ${container}: $($_.Exception.Message)"
        }
    }
    $env:DOCKER_CONFIG = $previousDockerConfig
}

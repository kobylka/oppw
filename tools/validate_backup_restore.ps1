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
$tempBase = Join-Path ([IO.Path]::GetTempPath()) ('oppw-recovery-drill-' + [Guid]::NewGuid().ToString('N'))
$dockerConfig = Join-Path $tempBase 'docker-config'
New-Item -ItemType Directory -Path $dockerConfig -Force | Out-Null
$previousDockerConfig = $env:DOCKER_CONFIG
$env:DOCKER_CONFIG = $dockerConfig
$sourceContainer = 'oppw-backup-source-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$restoreContainer = 'oppw-backup-restore-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$startedContainers = [System.Collections.Generic.List[string]]::new()
$stopwatch = [Diagnostics.Stopwatch]::StartNew()

function Wait-DisposableMysql {
    param([Parameter(Mandatory = $true)][string]$Container)
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        $savedErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $schemaName = (& $docker.Source exec $Container mysql -N -uroot `
                -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='oppw_monitor'" 2>$null)
            $schemaExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        if ($schemaExitCode -eq 0 -and ($schemaName -join '').Trim() -eq 'oppw_monitor') { return }
        Start-Sleep -Milliseconds 500
    }
    throw "Disposable MySQL container did not initialize: $Container"
}

function Invoke-DisposableSql {
    param(
        [Parameter(Mandatory = $true)][string]$Container,
        [Parameter(Mandatory = $true)][string]$Sql,
        [switch]$Database
    )
    $arguments = @('exec', '-i', $Container, 'mysql', '-uroot')
    if ($Database) { $arguments += '--database=oppw_monitor' }
    $Sql | & $docker.Source @arguments
    if ($LASTEXITCODE -ne 0) { throw "MySQL rejected SQL in disposable container: $Container" }
}

function Get-DisposableScalar {
    param(
        [Parameter(Mandatory = $true)][string]$Container,
        [Parameter(Mandatory = $true)][string]$Sql
    )
    $value = (& $docker.Source exec $Container mysql -N -uroot --database=oppw_monitor -e $Sql)
    if ($LASTEXITCODE -ne 0) { throw "MySQL scalar query failed in disposable container: $Container" }
    return ($value -join "`n").Trim()
}

function Get-TableDigest {
    param(
        [Parameter(Mandatory = $true)][string]$Container,
        [Parameter(Mandatory = $true)][string]$Table
    )
    $dump = (& $docker.Source exec $Container mysqldump -uroot `
        --no-create-info --skip-triggers --skip-comments --compact --order-by-primary `
        --hex-blob --set-gtid-purged=OFF oppw_monitor $Table)
    if ($LASTEXITCODE -ne 0) { throw "Could not digest restored table: $Table" }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($dump -join "`n"))
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
}

function Assert-MutationRejected {
    param(
        [Parameter(Mandatory = $true)][string]$Container,
        [Parameter(Mandatory = $true)][string]$Sql,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $docker.Source exec $Container mysql -uroot --database=oppw_monitor -e $Sql 2>$null | Out-Null
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    if ($exitCode -eq 0) { throw "Restored database accepted forbidden mutation: $Label" }
}

try {
    & $docker.Source info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not available.' }

    foreach ($container in @($sourceContainer, $restoreContainer)) {
        & $docker.Source run --detach --rm --name $container `
            --env 'MYSQL_ALLOW_EMPTY_PASSWORD=yes' `
            --env 'MYSQL_DATABASE=oppw_monitor' $Image | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not start disposable MySQL container: $container" }
        $startedContainers.Add($container)
        Wait-DisposableMysql -Container $container
    }

    $migrations = Get-Content -LiteralPath $orderFile |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' -and -not $_.StartsWith('#') }
    foreach ($migration in $migrations) {
        $path = Join-Path $sqlRoot $migration
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Migration listed but missing: $migration" }
        Invoke-DisposableSql -Container $sourceContainer -Sql (Get-Content -LiteralPath $path -Raw) -Database
    }

    $fixtureSql = @'
INSERT INTO strategy_specifications(spec_id,spec_hash,spec_key,spec_version,effective_from,created_at,strategy_build,execution_symbol,signal_symbol,document,document_hash)
VALUES ('11111111111111111111111111111111',REPEAT('a',64),'OPPW24','recovery-fixture','2025-01-01 00:00:00.000','2025-01-01 00:00:00.000','oppw-recovery','US100','NDX','{"fixture":true}',REPEAT('a',64));
INSERT INTO strategy_account_spec_assignments(strategy_key,spec_id,assigned_at,owner_id,fencing_token,strategy_build)
VALUES ('DEMO','11111111111111111111111111111111','2025-01-01 00:00:01.000','22222222222222222222222222222222',1,'oppw-recovery');
INSERT INTO strategy_decisions(strategy_key,decision_id,strategy_spec_id,strategy_spec_hash,recorded_at,first_received_at,last_received_at,payload,payload_hash)
VALUES ('DEMO','33333333333333333333333333333333','11111111111111111111111111111111',REPEAT('a',64),'2025-01-01 00:00:02.000','2025-01-01 00:00:02.000','2025-01-01 00:00:02.000','{"fixture":true}',REPEAT('b',64));
INSERT INTO strategy_execution_stages(strategy_key,stage_record_id,execution_id,decision_id,spec_id,position_ticket,stage,occurred_at,payload,payload_hash,received_at)
VALUES ('DEMO',REPEAT('4',64),'recovery-execution','33333333333333333333333333333333','11111111111111111111111111111111',9001,'SENT','2025-01-01 00:00:03.000','{"fixture":true}',REPEAT('c',64),'2025-01-01 00:00:03.100');
INSERT INTO strategy_fills(strategy_key,fill_record_id,execution_id,decision_id,spec_id,position_ticket,order_ticket,deal_ticket,side,filled_at,fill_price,payload,payload_hash,received_at)
VALUES ('DEMO',REPEAT('5',64),'recovery-execution','33333333333333333333333333333333','11111111111111111111111111111111',9001,9002,9003,'BUY','2025-01-01 00:00:04.000',20000.5,'{"fixture":true}',REPEAT('d',64),'2025-01-01 00:00:04.100');
INSERT INTO strategy_protection_changes(strategy_key,change_record_id,execution_id,decision_id,spec_id,position_ticket,occurred_at,change_stage,new_sl,reason,result,payload,payload_hash,received_at)
VALUES ('DEMO',REPEAT('6',64),'recovery-execution','33333333333333333333333333333333','11111111111111111111111111111111',9001,'2025-01-01 00:00:05.000','INITIAL',19000,'RECOVERY',TRUE,'{"fixture":true}',REPEAT('e',64),'2025-01-01 00:00:05.100');
INSERT INTO strategy_trade_ledger(strategy_key,trade_record_id,position_ticket,execution_id,decision_id,spec_id,transition_type,occurred_at,symbol,side,volume,price,reason,payload,payload_hash,received_at)
VALUES ('DEMO',REPEAT('7',64),9001,'recovery-execution','33333333333333333333333333333333','11111111111111111111111111111111','OPENED','2025-01-01 00:00:06.000','US100','BUY',0.01,20000.5,'RECOVERY','{"fixture":true}',REPEAT('f',64),'2025-01-01 00:00:06.100');
INSERT INTO account_cash_flows(strategy_key,occurred_at,flow_type,amount,balance_after,source,reference_key,note,payload_hash)
VALUES ('DEMO','2025-01-01 00:00:07.000','INITIAL',10000,10000,'RECOVERY','recovery-cash','fixture',REPEAT('1',64));
INSERT INTO strategy_service_control_events(request_id,strategy_key,role_name,desired_running,requested_at)
VALUES ('88888888888888888888888888888888','DEMO','EXECUTOR',TRUE,'2025-01-01 00:00:08.000');
UPDATE strategy_entry_rule_controls
SET gap_momentum_enabled=FALSE,revision=2,changed_at='2025-01-01 00:00:08.100'
WHERE strategy_key='DEMO';
INSERT INTO strategy_entry_rule_control_events(request_id,strategy_key,rule_key,enabled,requested_at)
VALUES ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','DEMO','GAP_MOMENTUM',FALSE,'2025-01-01 00:00:08.100');
INSERT INTO strategy_entry_rule_week_state(strategy_key,week_key,status,controls_revision,decision_id,inputs,changed_at)
VALUES ('DEMO','2025-W01','SKIP_ARITHMETIC',2,'33333333333333333333333333333333','{"arithmeticSum":-0.021}','2025-01-01 00:00:08.200');
INSERT INTO strategy_entry_rule_week_events(request_id,strategy_key,week_key,status,controls_revision,decision_id,owner_id,fencing_token,inputs,payload_hash,recorded_at)
VALUES ('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','DEMO','2025-W01','SKIP_ARITHMETIC',2,'33333333333333333333333333333333','22222222222222222222222222222222',1,'{"arithmeticSum":-0.021}',REPEAT('2',64),'2025-01-01 00:00:08.200');
INSERT INTO strategy_events(strategy_key,event_time,level,name,result,message,details,event_hash)
VALUES ('DEMO','2025-01-01 00:00:09.000','INFO','RECOVERY_FIXTURE',TRUE,'fixture','{"fixture":true}',REPEAT('9',64));
INSERT INTO strategy_equity_points(strategy_key,captured_minute,balance,equity,deposit,current_profit,position_ticket)
VALUES ('DEMO','2025-01-01 00:01:00',10000,10001,10000,1,9001);
INSERT INTO strategy_market_points(strategy_key,captured_minute,current_price,bid,ask,m1_open,m1_high,m1_low,m1_close,phase)
VALUES ('DEMO','2025-01-01 00:01:00',20000.5,20000.0,20001.0,19999.0,20002.0,19998.0,20000.5,'CASH');
INSERT INTO strategy_equity_daily(strategy_key,equity_day,first_captured_at,last_captured_at,open_balance,open_equity,close_balance,close_equity,minimum_equity,maximum_equity,sample_count)
VALUES ('DEMO','2024-12-31','2024-12-31 00:01:00','2024-12-31 23:59:00',9990,9991,10000,10000,9980,10010,1440);
'@
    Invoke-DisposableSql -Container $sourceContainer -Sql $fixtureSql -Database

    $containerDump = '/tmp/oppw-recovery.sql'
    & $docker.Source exec $sourceContainer mysqldump -uroot `
        --single-transaction --routines --triggers --events --hex-blob --set-gtid-purged=OFF `
        --databases oppw_monitor --result-file=$containerDump
    if ($LASTEXITCODE -ne 0) { throw 'Transactionally consistent backup creation failed.' }
    $hostDump = Join-Path $tempBase 'oppw-recovery.sql'
    & $docker.Source cp "${sourceContainer}:${containerDump}" $hostDump
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $hostDump -PathType Leaf)) {
        throw 'Could not copy disposable backup for restoration.'
    }
    & $docker.Source cp $hostDump "${restoreContainer}:${containerDump}"
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy disposable backup into restore target.' }
    & $docker.Source exec $restoreContainer sh -c "mysql -uroot < $containerDump"
    if ($LASTEXITCODE -ne 0) { throw 'Disposable backup restoration failed.' }

    $tables = @(
        'strategy_specifications', 'strategy_account_spec_assignments', 'strategy_decisions',
        'strategy_execution_stages', 'strategy_fills', 'strategy_protection_changes',
        'strategy_trade_ledger', 'account_cash_flows', 'strategy_service_control_events',
        'strategy_entry_rule_controls', 'strategy_entry_rule_control_events',
        'strategy_entry_rule_week_state', 'strategy_entry_rule_week_events',
        'strategy_events', 'strategy_equity_points', 'strategy_market_points', 'strategy_equity_daily'
    )
    foreach ($table in $tables) {
        $sourceCount = Get-DisposableScalar -Container $sourceContainer -Sql "SELECT COUNT(*) FROM $table"
        $restoreCount = Get-DisposableScalar -Container $restoreContainer -Sql "SELECT COUNT(*) FROM $table"
        if ($sourceCount -ne $restoreCount) { throw "Restored row count differs for ${table}: $sourceCount/$restoreCount" }
        $sourceDigest = Get-TableDigest -Container $sourceContainer -Table $table
        $restoreDigest = Get-TableDigest -Container $restoreContainer -Table $table
        if ($sourceDigest -ne $restoreDigest) { throw "Restored row digest differs for table: $table" }
    }

    $triggerCount = Get-DisposableScalar -Container $restoreContainer -Sql `
        "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='oppw_monitor' AND TRIGGER_NAME REGEXP '_no_(update|delete)$'"
    if ([int]$triggerCount -ne 23) { throw "Restored immutability-trigger validation failed: $triggerCount/23" }
    Assert-MutationRejected -Container $restoreContainer `
        -Sql "UPDATE strategy_decisions SET outcome='MUTATED' WHERE decision_id='33333333333333333333333333333333'" `
        -Label 'strategy decision update'
    Assert-MutationRejected -Container $restoreContainer `
        -Sql "DELETE FROM strategy_service_control_events WHERE request_id='88888888888888888888888888888888'" `
        -Label 'service-control audit deletion'
    Assert-MutationRejected -Container $restoreContainer `
        -Sql "DELETE FROM strategy_entry_rule_week_events WHERE request_id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'" `
        -Label 'entry-rule weekly audit deletion'
    Assert-MutationRejected -Container $restoreContainer `
        -Sql "DELETE FROM strategy_market_points WHERE strategy_key='DEMO'" `
        -Label 'minute market OHLC deletion'

    $stopwatch.Stop()
    if ($stopwatch.Elapsed.TotalMinutes -ge 30) {
        throw "Disposable recovery drill exceeded its 30-minute RTO target: $($stopwatch.Elapsed)"
    }
    Write-Host "BACKUP RESTORE VALIDATION PASSED tables=$($tables.Count) immutable_triggers=$triggerCount rpo=0 elapsed_seconds=$([math]::Round($stopwatch.Elapsed.TotalSeconds, 1)) image=$Image"
} finally {
    foreach ($container in $startedContainers) {
        try {
            & $docker.Source rm --force $container 2>$null | Out-Null
        } catch {
            Write-Warning "Could not remove disposable MySQL container ${container}: $($_.Exception.Message)"
        }
    }
    $env:DOCKER_CONFIG = $previousDockerConfig
    $resolvedTemp = [IO.Path]::GetFullPath($tempBase)
    $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedTemp)) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}

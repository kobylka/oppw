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
$password = [Guid]::NewGuid().ToString('N')
$containerStarted = $false

try {
    & $docker.Source info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine is not available.' }

    & $docker.Source run --detach --rm --name $container `
        --env "MYSQL_ROOT_PASSWORD=$password" `
        --env 'MYSQL_DATABASE=oppw_monitor' $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start temporary MySQL container.' }
    $containerStarted = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & $docker.Source exec $container mysqladmin ping --silent -uroot "-p$password" 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Temporary MySQL did not become ready within 30 seconds.' }

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
            & $docker.Source exec -i $container mysql -uroot "-p$password" --database=oppw_monitor
        if ($LASTEXITCODE -ne 0) { throw "MySQL rejected migration: $migration" }
    }

    $tableQuery = "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='oppw_monitor' AND TABLE_NAME IN ('strategy_specifications','strategy_account_spec_assignments','strategy_decisions','strategy_execution_stages','strategy_fills','strategy_protection_changes','strategy_trade_ledger','account_cash_flows');"
    $tableCount = (& $docker.Source exec $container mysql -N -uroot "-p$password" --database=oppw_monitor -e $tableQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$tableCount -ne 8) { throw "Authority-table validation failed: $tableCount/8" }

    $triggerQuery = "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='oppw_monitor' AND TRIGGER_NAME REGEXP '_no_(update|delete)$';"
    $triggerCount = (& $docker.Source exec $container mysql -N -uroot "-p$password" --database=oppw_monitor -e $triggerQuery).Trim()
    if ($LASTEXITCODE -ne 0 -or [int]$triggerCount -ne 16) { throw "Immutability-trigger validation failed: $triggerCount/16" }

    Write-Host "MYSQL VALIDATION PASSED tables=$tableCount triggers=$triggerCount image=$Image"
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

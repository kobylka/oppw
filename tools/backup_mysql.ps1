[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ConfigPath = '',
    [string]$ConfigHelperPath = '',
    [string]$DatabaseHost = 'eloski.eu',
    [string]$Destination = 'D:\OPPW-Backups\mysql',
    [string]$DockerPath = '',
    [string]$PhpPath = '',
    [string]$Image = 'mysql:8.4',
    [int]$KeepDaily = 35,
    [int]$KeepMonthly = 12,
    [int]$KeepLogDays = 180,
    [switch]$ConnectivityOnly
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
if ($ConfigPath -eq '') { $ConfigPath = Join-Path $root 'Mobile\backend\config.php' }
if ($ConfigHelperPath -eq '') { $ConfigHelperPath = Join-Path $root 'tools\write_mysql_client_config.php' }
$ConfigPath = (Resolve-Path -LiteralPath $ConfigPath -ErrorAction Stop).Path
$ConfigHelperPath = (Resolve-Path -LiteralPath $ConfigHelperPath -ErrorAction Stop).Path
if ($DockerPath -eq '') {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCommand) { throw 'Docker is required for production MySQL backups.' }
    $DockerPath = $dockerCommand.Source
}
if ($PhpPath -eq '') {
    $phpCommand = Get-Command php -ErrorAction SilentlyContinue
    if (-not $phpCommand) { throw 'PHP CLI is required to read the private backend configuration.' }
    $PhpPath = $phpCommand.Source
}
$DockerPath = (Resolve-Path -LiteralPath $DockerPath -ErrorAction Stop).Path
$PhpPath = (Resolve-Path -LiteralPath $PhpPath -ErrorAction Stop).Path
if ($KeepDaily -lt 7 -or $KeepDaily -gt 365) { throw 'KeepDaily must be between 7 and 365.' }
if ($KeepMonthly -lt 1 -or $KeepMonthly -gt 120) { throw 'KeepMonthly must be between 1 and 120.' }
if ($KeepLogDays -lt 30 -or $KeepLogDays -gt 3650) { throw 'KeepLogDays must be between 30 and 3650.' }
if ($DatabaseHost -notmatch '^[A-Za-z0-9.-]+$') { throw 'DatabaseHost is invalid.' }

function ConvertTo-NativeArguments([string[]]$Values) {
    return ($Values | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' '
}

function Start-DockerProcess([string[]]$Arguments, [bool]$RedirectOutput, [bool]$RedirectInput) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $DockerPath
    $start.Arguments = ConvertTo-NativeArguments $Arguments
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardOutput = $RedirectOutput
    $start.RedirectStandardInput = $RedirectInput
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'Could not start Docker.' }
    return $process
}

function Invoke-Docker([string[]]$Arguments, [switch]$Capture) {
    if ($Capture) {
        $output = & $DockerPath @Arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Docker failed: $($output -join [Environment]::NewLine)" }
        return ($output -join "`n").Trim()
    }
    & $DockerPath @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $($Arguments -join ' ')" }
}

function Wait-MySql([string]$Container) {
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        $process = Start-DockerProcess -Arguments @(
            'exec', $Container, 'mysql', '-N', '-uroot', '-e', 'SELECT @@port'
        ) -RedirectOutput $true -RedirectInput $false
        try {
            $stderrTask = $process.StandardError.ReadToEndAsync()
            $port = $process.StandardOutput.ReadToEnd()
            $process.WaitForExit()
            $null = $stderrTask.GetAwaiter().GetResult()
            $ready = $process.ExitCode -eq 0 -and $port.Trim() -eq '3306'
        } finally {
            if (-not $process.HasExited) { $process.Kill() }
            $process.Dispose()
        }
        if ($ready) { return }
        Start-Sleep -Milliseconds 500
    }
    throw 'Disposable restore database did not initialize within 40 seconds.'
}

function Test-EncryptedPath([string]$Path) {
    $attributes = [IO.File]::GetAttributes($Path)
    return ($attributes -band [IO.FileAttributes]::Encrypted) -ne 0
}

function Write-GzipDump([string]$DefaultsPath, [string]$Database, [string]$OutputPath) {
    $mount = "type=bind,source=$DefaultsPath,target=/run/host/oppw.cnf,readonly"
    $dumpCommand = 'cp /run/host/oppw.cnf /tmp/oppw.cnf && chmod 600 /tmp/oppw.cnf && exec mysqldump ' `
        + '--defaults-extra-file=/tmp/oppw.cnf --single-transaction --quick --routines --triggers ' `
        + '--hex-blob --no-tablespaces --max-allowed-packet=1G --set-gtid-purged=OFF --databases ' + $Database
    $arguments = @(
        'run', '--rm', '--mount', $mount, $Image, 'sh', '-c', $dumpCommand
    )
    $process = Start-DockerProcess -Arguments $arguments -RedirectOutput $true -RedirectInput $false
    $stderrTask = $process.StandardError.ReadToEndAsync()
    try {
        $file = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $gzip = [IO.Compression.GZipStream]::new($file, [IO.Compression.CompressionLevel]::Optimal, $true)
            try { $process.StandardOutput.BaseStream.CopyTo($gzip) }
            finally { $gzip.Dispose() }
        } finally {
            $file.Dispose()
        }
        $process.WaitForExit()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "mysqldump failed: $stderr" }
    } finally {
        if (-not $process.HasExited) { $process.Kill() }
        $process.Dispose()
    }
}

function Restore-And-Verify([string]$BackupPath, [string]$Database) {
    $container = 'oppw-production-restore-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $started = $false
    try {
        Invoke-Docker @('run', '--detach', '--rm', '--name', $container, '--env', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes', $Image, '--max-allowed-packet=1G')
        $started = $true
        Wait-MySql $container
        $process = Start-DockerProcess -Arguments @('exec', '-i', $container, 'mysql', '-uroot', '--max-allowed-packet=1G') -RedirectOutput $true -RedirectInput $true
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $copyError = $null
        try {
            $file = [IO.File]::OpenRead($BackupPath)
            try {
                $gzip = [IO.Compression.GZipStream]::new($file, [IO.Compression.CompressionMode]::Decompress, $false)
                try { $gzip.CopyTo($process.StandardInput.BaseStream) }
                catch { $copyError = $_ }
                finally { $gzip.Dispose() }
            } finally {
                $file.Dispose()
            }
            $process.StandardInput.Close()
            $process.WaitForExit()
            $stderr = $stderrTask.GetAwaiter().GetResult()
            $null = $stdoutTask.GetAwaiter().GetResult()
            if ($process.ExitCode -ne 0) {
                $savedPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = 'Continue'
                    $serverLog = (& $DockerPath logs --tail 80 $container 2>&1) -join "`n"
                } finally {
                    $ErrorActionPreference = $savedPreference
                }
                throw "Production backup restore failed: $stderr`nDisposable MySQL log:`n$serverLog"
            }
            if ($copyError) { throw "Production backup restore stream failed: $($copyError.Exception.Message)" }
        } finally {
            if (-not $process.HasExited) { $process.Kill() }
            $process.Dispose()
        }

        $safeDatabase = $Database.Replace("'", "''")
        $authority = Invoke-Docker @(
            'exec', $container, 'mysql', '-N', '-uroot', '-e',
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$safeDatabase' AND TABLE_NAME IN ('strategy_specifications','strategy_account_spec_assignments','strategy_decisions','strategy_execution_stages','strategy_fills','strategy_protection_changes','strategy_trade_ledger','account_cash_flows','strategy_entry_rule_control_events','strategy_entry_rule_week_state','strategy_entry_rule_week_events','strategy_position_rule_control_events','strategy_position_rule_trigger_events')"
        ) -Capture
        if ([int]$authority -ne 13) { throw "Restored authority table count is $authority/13." }
        $operational = Invoke-Docker @(
            'exec', $container, 'mysql', '-N', '-uroot', '-e',
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$safeDatabase' AND TABLE_NAME IN ('strategy_events','strategy_equity_points','strategy_market_points','strategy_service_control_events','strategy_entry_rule_controls','strategy_position_rule_controls')"
        ) -Capture
        if ([int]$operational -ne 6) { throw "Restored operational table count is $operational/6." }
        $triggers = Invoke-Docker @(
            'exec', $container, 'mysql', '-N', '-uroot', '-e',
            "SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='$safeDatabase'"
        ) -Capture
        if ([int]$triggers -lt 20) { throw "Restored trigger count is unexpectedly low: $triggers." }
        return [ordered]@{ authorityTables = [int]$authority; operationalTables = [int]$operational; triggers = [int]$triggers }
    } finally {
        if ($started) {
            try { & $DockerPath rm --force $container 2>$null | Out-Null } catch {}
        }
    }
}

function Remove-ExpiredBackups([string]$BackupRoot, [int]$DailyDays, [int]$MonthlyMonths) {
    $now = [DateTime]::UtcNow
    $dailyCutoff = $now.AddDays(-$DailyDays)
    $monthlyCutoff = $now.AddMonths(-$MonthlyMonths)
    $candidates = @()
    foreach ($file in Get-ChildItem -LiteralPath $BackupRoot -Filter 'oppw-mysql-*.sql.gz' -File) {
        if ($file.BaseName -notmatch '^oppw-mysql-(\d{8}T\d{6}Z)\.sql$') { continue }
        $timestamp = [DateTime]::ParseExact($Matches[1], 'yyyyMMddTHHmmssZ', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal)
        $candidates += [pscustomobject]@{ File = $file; Timestamp = $timestamp; Month = $timestamp.ToString('yyyyMM') }
    }
    $monthlyKeep = @{}
    foreach ($item in $candidates | Where-Object { $_.Timestamp -lt $dailyCutoff -and $_.Timestamp -ge $monthlyCutoff } | Sort-Object Timestamp -Descending) {
        if (-not $monthlyKeep.ContainsKey($item.Month)) { $monthlyKeep[$item.Month] = $item.File.FullName }
    }
    foreach ($item in $candidates) {
        $keep = $item.Timestamp -ge $dailyCutoff -or ($monthlyKeep[$item.Month] -eq $item.File.FullName)
        if ($keep) { continue }
        foreach ($path in @($item.File.FullName, $item.File.FullName + '.sha256', $item.File.FullName + '.json')) {
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                Remove-Item -LiteralPath $path -Force
                Write-Host "Expired production backup artifact: $path"
            }
        }
    }
}

function Remove-ExpiredLogs([string]$LogRoot, [int]$LogDays) {
    $cutoff = [DateTime]::UtcNow.AddDays(-$LogDays)
    foreach ($file in Get-ChildItem -LiteralPath $LogRoot -Filter 'oppw-backup-*.log' -File) {
        if ($file.LastWriteTimeUtc -ge $cutoff) { continue }
        Remove-Item -LiteralPath $file.FullName -Force
    }
}

$destinationFull = [IO.Path]::GetFullPath($Destination)
$destinationRoot = [IO.Path]::GetPathRoot($destinationFull)
if ($destinationFull.TrimEnd('\') -eq $destinationRoot.TrimEnd('\') -or $destinationFull.Length -lt 10) {
    throw 'Production backup destination is too broad.'
}
if (-not (Test-Path -LiteralPath $destinationFull -PathType Container)) {
    throw "Production backup destination does not exist: $destinationFull"
}
if (-not (Test-EncryptedPath $destinationFull)) {
    throw "Production backup destination is not EFS encrypted: $destinationFull"
}

$transcriptStarted = $false
$logDirectory = Join-Path $destinationFull 'logs'
if (-not $ConnectivityOnly) {
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    if (-not (Test-EncryptedPath $logDirectory)) {
        throw "Production backup log directory did not inherit EFS encryption: $logDirectory"
    }
    $logStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $logPath = Join-Path $logDirectory ("oppw-backup-$logStamp.log")
    Start-Transcript -Path $logPath -Force | Out-Null
    $transcriptStarted = $true
    if (-not (Test-EncryptedPath $logPath)) { throw 'Production backup log did not inherit EFS encryption.' }
}

$lockPath = Join-Path $destinationFull '.oppw-backup.lock'
$lock = $null
$tempBase = Join-Path ([IO.Path]::GetTempPath()) ('oppw-production-backup-' + [Guid]::NewGuid().ToString('N'))
try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    New-Item -ItemType Directory -Path $tempBase -Force | Out-Null
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $tempBase /inheritance:r /grant:r "*${sid}:(OI)(CI)(F)" '*S-1-5-18:(OI)(CI)(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not protect temporary database credentials.' }
    $defaultsPath = Join-Path $tempBase 'mysql.cnf'
    $metadataRaw = & $PhpPath $ConfigHelperPath $ConfigPath $defaultsPath $DatabaseHost
    if ($LASTEXITCODE -ne 0) { throw 'Could not derive MySQL client settings from backend configuration.' }
    $metadata = $metadataRaw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $defaultsPath -PathType Leaf)) { throw 'Temporary MySQL client settings were not created.' }
    Write-Host "Production MySQL target reachable configuration host=$($metadata.host) port=$($metadata.port) database=$($metadata.database) tls=required"

    if ($ConnectivityOnly) {
        $mount = "type=bind,source=$defaultsPath,target=/run/host/oppw.cnf,readonly"
        $probe = Invoke-Docker @(
            'run', '--rm', '--mount', $mount, $Image, 'sh', '-c',
            'cp /run/host/oppw.cnf /tmp/oppw.cnf && chmod 600 /tmp/oppw.cnf && exec mysql --defaults-extra-file=/tmp/oppw.cnf -N -e ''SELECT 1'''
        ) -Capture
        if ([string]::IsNullOrWhiteSpace($probe)) { throw 'Production MySQL connectivity probe returned no result.' }
        Write-Host 'PRODUCTION MYSQL CONNECTIVITY PASSED tls=required'
        return
    }

    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $partial = Join-Path $destinationFull ("oppw-mysql-$stamp.sql.gz.partial")
    $final = Join-Path $destinationFull ("oppw-mysql-$stamp.sql.gz")
    try {
        Write-GzipDump -DefaultsPath $defaultsPath -Database ([string]$metadata.database) -OutputPath $partial
        if ((Get-Item -LiteralPath $partial).Length -le 0) { throw 'Production backup is empty.' }
        if (-not (Test-EncryptedPath $partial)) { throw 'Production backup file did not inherit EFS encryption.' }
        $restore = Restore-And-Verify -BackupPath $partial -Database ([string]$metadata.database)
        Move-Item -LiteralPath $partial -Destination $final
        $hash = (Get-FileHash -LiteralPath $final -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText($final + '.sha256', "$hash  $([IO.Path]::GetFileName($final))`r`n", [Text.UTF8Encoding]::new($false))
        $manifest = [ordered]@{
            createdAt = [DateTime]::UtcNow.ToString('o')
            database = [string]$metadata.database
            host = [string]$metadata.host
            port = [int]$metadata.port
            transport = 'TLS_REQUIRED'
            encryption = 'WINDOWS_EFS'
            compression = 'GZIP'
            mysqlScheduledEvents = 'NOT_USED_BY_CANONICAL_SCHEMA'
            sha256 = $hash
            bytes = (Get-Item -LiteralPath $final).Length
            restoreVerified = $true
            restoredAuthorityTables = $restore.authorityTables
            restoredOperationalTables = $restore.operationalTables
            restoredTriggers = $restore.triggers
        }
        [IO.File]::WriteAllText($final + '.json', ($manifest | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
        foreach ($artifact in @($final, ($final + '.sha256'), ($final + '.json'))) {
            if (-not (Test-EncryptedPath $artifact)) { throw "Production backup artifact is not EFS encrypted: $artifact" }
        }
        Remove-ExpiredBackups -BackupRoot $destinationFull -DailyDays $KeepDaily -MonthlyMonths $KeepMonthly
        Remove-ExpiredLogs -LogRoot $logDirectory -LogDays $KeepLogDays
        Write-Host "PRODUCTION MYSQL BACKUP PASSED path=$final sha256=$hash restore_verified=true"
    } catch {
        if (Test-Path -LiteralPath $partial -PathType Leaf) { Remove-Item -LiteralPath $partial -Force }
        throw
    }
} finally {
    try {
        if ($lock) { $lock.Dispose() }
        $resolvedTemp = [IO.Path]::GetFullPath($tempBase)
        $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedTemp)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    } finally {
        if ($transcriptStarted) { Stop-Transcript | Out-Null }
    }
}

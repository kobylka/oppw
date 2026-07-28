[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$DatabaseHost = 'eloski.eu',
    [string]$Destination = 'D:\OPPW-Backups\mysql',
    [string]$DailyAt = '02:15',
    [string]$TaskName = 'OPPW MySQL Production Backup',
    [string]$DockerPath = '',
    [string]$PhpPath = '',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
if ($Uninstall) {
    if ($PSCmdlet.ShouldProcess($TaskName, 'Remove scheduled production backup task')) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    return
}

$root = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
$sourceRunner = Join-Path $root 'tools\backup_mysql.ps1'
$sourceHelper = Join-Path $root 'tools\write_mysql_client_config.php'
$configPath = Join-Path $root 'Mobile\backend\config.php'
foreach ($path in @($sourceRunner, $sourceHelper, $configPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required production backup file is missing: $path" }
}
if ($DockerPath -eq '') {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw 'Docker is required.' }
    $DockerPath = $docker.Source
}
if ($PhpPath -eq '') {
    $php = Get-Command php -ErrorAction SilentlyContinue
    if (-not $php) { throw 'PHP CLI is required. Pass -PhpPath when it is not on PATH.' }
    $PhpPath = $php.Source
}
$DockerPath = (Resolve-Path -LiteralPath $DockerPath -ErrorAction Stop).Path
$PhpPath = (Resolve-Path -LiteralPath $PhpPath -ErrorAction Stop).Path
try { $scheduledTime = [DateTime]::ParseExact($DailyAt, 'HH:mm', [Globalization.CultureInfo]::InvariantCulture) }
catch { throw 'DailyAt must use 24-hour HH:mm format.' }

$destinationFull = [IO.Path]::GetFullPath($Destination)
$destinationRoot = [IO.Path]::GetPathRoot($destinationFull)
if ($destinationFull.TrimEnd('\') -eq $destinationRoot.TrimEnd('\') -or $destinationFull.Length -lt 10) {
    throw 'Production backup destination is too broad.'
}
if ($PSCmdlet.ShouldProcess($destinationFull, 'Create and enable Windows EFS encryption')) {
    New-Item -ItemType Directory -Path $destinationFull -Force | Out-Null
    & cipher.exe /E $destinationFull | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not enable EFS encryption on the production backup destination.' }
    if (([IO.File]::GetAttributes($destinationFull) -band [IO.FileAttributes]::Encrypted) -eq 0) {
        throw 'Production backup destination is not EFS encrypted.'
    }
}

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'OPPW\mysql-backup'
if ($PSCmdlet.ShouldProcess($runtimeRoot, 'Install protected production backup runner')) {
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    Copy-Item -LiteralPath $sourceRunner -Destination (Join-Path $runtimeRoot 'backup_mysql.ps1') -Force
    Copy-Item -LiteralPath $sourceHelper -Destination (Join-Path $runtimeRoot 'write_mysql_client_config.php') -Force
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $runtimeRoot /inheritance:r /grant:r "*${sid}:(OI)(CI)(F)" '*S-1-5-18:(OI)(CI)(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not protect the installed backup runner.' }
}

$runner = Join-Path $runtimeRoot 'backup_mysql.ps1'
$helper = Join-Path $runtimeRoot 'write_mysql_client_config.php'
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$actionArguments = @(
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $runner,
    '-RepoRoot', $root, '-ConfigPath', $configPath, '-ConfigHelperPath', $helper,
    '-DatabaseHost', $DatabaseHost, '-Destination', $destinationFull,
    '-DockerPath', $DockerPath, '-PhpPath', $PhpPath, '-KeepDaily', '35', '-KeepMonthly', '12',
    '-KeepLogDays', '180'
)
$quotedArguments = ($actionArguments | ForEach-Object {
    if ($_ -match '[\s"]') { '"' + $_.Replace('"', '\"') + '"' } else { $_ }
}) -join ' '
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $quotedArguments -WorkingDirectory $runtimeRoot
$start = Get-Date -Hour $scheduledTime.Hour -Minute $scheduledTime.Minute -Second 0
$trigger = New-ScheduledTaskTrigger -Daily -At $start
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, "Register daily scheduled task at $DailyAt")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description 'TLS MySQL dump, EFS storage, SHA-256, and disposable restore verification.' -Force | Out-Null
}
Write-Host "PRODUCTION MYSQL BACKUP TASK INSTALLED task='$TaskName' schedule=$DailyAt destination=$destinationFull user=$user"

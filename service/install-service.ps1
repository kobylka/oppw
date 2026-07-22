[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [ValidateSet('Master','Backup')][string]$NodeRole = 'Master',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = '',
    [string]$ControlUrl = 'https://eloski.eu/oppw-backend/service-control.php',
    [string]$WriteToken = '',
    [string]$RuntimeUser = '',
    [PSCredential]$ServiceCredential,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$serviceName = 'OPPWContinuousSupervisor'
function Invoke-ScCommand([string[]]$Arguments) {
    & sc.exe @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "sc.exe failed ($LASTEXITCODE): $($Arguments -join ' ')" }
}
function Remove-ServiceRegistration([string]$Name) {
    & sc.exe delete $Name | Out-Null
    $exitCode = $LASTEXITCODE
    # ERROR_SERVICE_MARKED_FOR_DELETE means an earlier delete already succeeded.
    if ($exitCode -ne 0 -and $exitCode -ne 1072) {
        throw "sc.exe failed ($exitCode): delete $Name"
    }
    for ($attempt = 0; $attempt -lt 60 -and (Get-Service -Name $Name -ErrorAction SilentlyContinue); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
    if (Get-Service -Name $Name -ErrorAction SilentlyContinue) {
        throw "Service $Name is marked for deletion but is still held open. Close Services (services.msc), Computer Management, and any service-properties windows, then run the installer again."
    }
}
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer from an elevated PowerShell session.'
}
if ($Uninstall) {
    if ($PSCmdlet.ShouldProcess($serviceName, 'Stop and remove Windows service')) {
        $existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($existing -and $existing.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force; $existing.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(40)) }
        if ($existing) { Remove-ServiceRegistration $serviceName }
    }
    return
}

$root = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
if ($PythonPath -eq '') {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'Python is required. Pass -PythonPath when it is not on PATH.' }
    $PythonPath = $python.Source
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath -ErrorAction Stop).Path
foreach ($relative in @('VERSION','mt5\oppw_mt5_continuous.py','mt5\demo\demo_mt5_config.py','mt5\real\real_mt5_config.py','service\oppw_windows_supervisor.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) { throw "Required runtime file missing: $relative" }
}
if (-not $ControlUrl.StartsWith('https://', [StringComparison]::OrdinalIgnoreCase)) { throw 'ControlUrl must use HTTPS.' }
if ($WriteToken -eq '') {
    $secure = Read-Host 'Backend MT5 write token' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $WriteToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if ([string]::IsNullOrWhiteSpace($WriteToken)) { throw 'Backend write token is required.' }
if ($RuntimeUser -eq '' -and $ServiceCredential) { $RuntimeUser = $ServiceCredential.UserName }
if ($RuntimeUser -eq '') {
    $RuntimeUser = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
}
try {
    $runtimeIdentity = [Security.Principal.NTAccount]::new($RuntimeUser)
    $runtimeSid = $runtimeIdentity.Translate([Security.Principal.SecurityIdentifier]).Value
} catch {
    throw "RuntimeUser '$RuntimeUser' is not a resolvable Windows account."
}

$programData = Join-Path $env:ProgramData 'OPPW'
$binDir = Join-Path $programData 'bin'
$configPath = Join-Path $programData 'service.json'
$hostPath = Join-Path $binDir 'OPPWServiceHost.exe'
$supervisorPath = Join-Path $root 'service\oppw_windows_supervisor.py'
New-Item -ItemType Directory -Path $programData -Force | Out-Null
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
$packagedHost = Join-Path $root 'artifacts\OPPWServiceHost.exe'
if (Test-Path -LiteralPath $packagedHost -PathType Leaf) {
    Copy-Item -LiteralPath $packagedHost -Destination $hostPath -Force
} else {
    & (Join-Path $root 'service\build-service-host.ps1') -RepoRoot $root -OutputPath $hostPath
}
$existing = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } else { $null }
$nodeId = if ($existing -and "$($existing.nodeRole)" -eq $NodeRole.ToUpperInvariant() -and "$($existing.nodeId)" -match '^[a-f0-9]{32}$') { "$($existing.nodeId)" } else { [Guid]::NewGuid().ToString('N') }
$config = [ordered]@{
    nodeId = $nodeId
    nodeRole = $NodeRole.ToUpperInvariant()
    repoRoot = $root
    pythonPath = $PythonPath
    controlUrl = $ControlUrl
    writeToken = $WriteToken
    pollSeconds = 3
    assignmentTtlSeconds = 15
    stopGraceSeconds = 15
    restartDelaySeconds = 5
    companionStartDelaySeconds = 70
    runtimeDir = (Join-Path $programData 'runtime')
    logDir = (Join-Path $programData 'logs')
}
[IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
$serviceAccount = $RuntimeUser
& icacls.exe $programData /grant:r "*${runtimeSid}:(OI)(CI)(M)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not grant the service account access to OPPW runtime directories.' }
# Numeric SIDs are stable across localized Windows installations. icacls
# requires the leading asterisk when a trustee is supplied as a SID.
& icacls.exe $configPath /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' "*${runtimeSid}:(R)" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect the private service configuration.' }

$binaryPath = '"' + $hostPath + '" "' + $PythonPath + '" "' + $supervisorPath + '" "' + $configPath + '" "' + $runtimeSid + '"'
if ($PSCmdlet.ShouldProcess($serviceName, 'Create and start Windows service')) {
    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existingService) {
        if ($existingService.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force; $existingService.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(40)) }
        Remove-ServiceRegistration $serviceName
    }
    New-Service -Name $serviceName -BinaryPathName $binaryPath -DisplayName 'OPPW Continuous Supervisor' `
        -Description 'Maintains the assigned DEMO/REAL executor and publisher processes with global master/backup fencing.' `
        -StartupType Automatic | Out-Null
    Invoke-ScCommand @('config', $serviceName, 'start=', 'delayed-auto')
    Invoke-ScCommand @('failure', $serviceName, 'reset=', '86400', 'actions=', 'restart/5000/restart/15000/restart/30000')
    Start-Service -Name $serviceName
    (Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(40))
}
Write-Host "OPPW SERVICE INSTALLED role=$($NodeRole.ToUpperInvariant()) node=$nodeId config=$configPath"

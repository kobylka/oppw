[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [ValidateSet('Master','Backup')][string]$NodeRole = 'Master',
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = '',
    [string]$ControlUrl = 'https://eloski.eu/oppw-backend/service-control.php',
    [string]$WriteToken = '',
    [string]$RuntimeUser = '',
    [string[]]$Accounts = @(),
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
function Set-ExactPathAcl {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][Security.Principal.SecurityIdentifier]$RuntimeSid,
        [ValidateSet('None','Traverse','Read','Modify')][string]$RuntimeAccess = 'None',
        [switch]$RuntimeChildrenInherit
    )

    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleSpecific($rule)
    }

    $systemIdentity = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    $administratorsIdentity = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $acl.SetOwner($administratorsIdentity)

    $isDirectory = Test-Path -LiteralPath $Path -PathType Container
    $childInheritance = if ($isDirectory) {
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    $propagation = [Security.AccessControl.PropagationFlags]::None
    $allow = [Security.AccessControl.AccessControlType]::Allow
    foreach ($identity in @($systemIdentity, $administratorsIdentity)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $identity,
            [Security.AccessControl.FileSystemRights]::FullControl,
            $childInheritance,
            $propagation,
            $allow
        ))
    }

    if ($RuntimeAccess -ne 'None') {
        $runtimeRights = switch ($RuntimeAccess) {
            'Traverse' { [Security.AccessControl.FileSystemRights]::ReadAndExecute }
            'Read' { [Security.AccessControl.FileSystemRights]::Read }
            'Modify' { [Security.AccessControl.FileSystemRights]::Modify }
        }
        $runtimeInheritance = if ($isDirectory -and $RuntimeChildrenInherit) {
            $childInheritance
        } else {
            [Security.AccessControl.InheritanceFlags]::None
        }
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            $RuntimeSid,
            $runtimeRights,
            $runtimeInheritance,
            $propagation,
            $allow
        ))
    }

    Set-Acl -LiteralPath $Path -AclObject $acl
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
foreach ($relative in @('VERSION','mt5\oppw_mt5_continuous.py','service\oppw_windows_supervisor.py')) {
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
$runtimeDir = Join-Path $programData 'runtime'
$logDir = Join-Path $programData 'logs'
$configPath = Join-Path $programData 'service.json'
$hostPath = Join-Path $binDir 'OPPWServiceHost.exe'
$supervisorPath = Join-Path $root 'service\oppw_windows_supervisor.py'
New-Item -ItemType Directory -Path $programData -Force | Out-Null
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$runtimeSecurityIdentifier = [Security.Principal.SecurityIdentifier]::new($runtimeSid)

# The LocalSystem service executable and its containing directory are a
# privileged code boundary. The runtime user may traverse the root and write
# only runtime/log data; it cannot replace the host, its directory, or config.
Set-ExactPathAcl -Path $programData -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Traverse -RuntimeChildrenInherit
Set-ExactPathAcl -Path $binDir -RuntimeSid $runtimeSecurityIdentifier
Set-ExactPathAcl -Path $runtimeDir -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Modify -RuntimeChildrenInherit
Set-ExactPathAcl -Path $logDir -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Modify -RuntimeChildrenInherit

$packagedHost = Join-Path $root 'artifacts\OPPWServiceHost.exe'
if (Test-Path -LiteralPath $packagedHost -PathType Leaf) {
    Copy-Item -LiteralPath $packagedHost -Destination $hostPath -Force
} else {
    & (Join-Path $root 'service\build-service-host.ps1') -RepoRoot $root -OutputPath $hostPath
}
Set-ExactPathAcl -Path $hostPath -RuntimeSid $runtimeSecurityIdentifier
$existing = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } else { $null }
$accountSpecifications = if ($Accounts.Count -gt 0) {
    @($Accounts)
} elseif ($existing -and $existing.managedAccounts) {
    @($existing.managedAccounts | ForEach-Object { "$($_.accountType):$($_.accountKey)" })
} else {
    @('DEMO:DEMO', 'REAL:REAL')
}
if ($accountSpecifications.Count -lt 1 -or $accountSpecifications.Count -gt 8) {
    throw 'Accounts must configure between 1 and 8 account descriptors.'
}
$seenAccountKeys = @{}
$managedAccounts = @(
    foreach ($specification in $accountSpecifications) {
        $parts = @("$specification" -split ':', 2)
        if ($parts.Count -ne 2) {
            throw "Invalid account descriptor '$specification'. Use DEMO:ACCOUNT_KEY or REAL:ACCOUNT_KEY."
        }
        $accountType = $parts[0].Trim().ToUpperInvariant()
        $accountKey = $parts[1].Trim().ToUpperInvariant()
        if ($accountType -notin @('DEMO', 'REAL')) {
            throw "Invalid account type in '$specification'. Use DEMO or REAL."
        }
        if ($accountKey -notmatch '^[A-Z0-9][A-Z0-9_-]{0,63}$') {
            throw "Invalid account key in '$specification'. Use 1-64 letters, digits, underscores, or hyphens."
        }
        if ($accountKey -in @('DEMO', 'REAL') -and $accountKey -ne $accountType) {
            throw "Reserved account key $accountKey must use account type $accountKey."
        }
        if ($seenAccountKeys.ContainsKey($accountKey)) {
            throw "Duplicate account key in Accounts: $accountKey"
        }
        $seenAccountKeys[$accountKey] = $true
        $fileName = if ($accountKey -eq $accountType) {
            "$($accountType.ToLowerInvariant())_mt5_config.py"
        } else {
            "$($accountKey.ToLowerInvariant())_mt5_config.py"
        }
        $relativeConfig = "mt5\$($accountType.ToLowerInvariant())\$fileName"
        if (-not (Test-Path -LiteralPath (Join-Path $root $relativeConfig) -PathType Leaf)) {
            throw "Required private account configuration missing: $relativeConfig"
        }
        [ordered]@{ accountKey = $accountKey; accountType = $accountType }
    }
)
$nodeId = if ($existing -and "$($existing.nodeRole)" -eq $NodeRole.ToUpperInvariant() -and "$($existing.nodeId)" -match '^[a-f0-9]{32}$') { "$($existing.nodeId)" } else { [Guid]::NewGuid().ToString('N') }
$config = [ordered]@{
    nodeId = $nodeId
    nodeRole = $NodeRole.ToUpperInvariant()
    repoRoot = $root
    pythonPath = $PythonPath
    controlUrl = $ControlUrl
    writeToken = $WriteToken
    managedAccounts = $managedAccounts
    pollSeconds = 3
    assignmentTtlSeconds = 15
    stopGraceSeconds = 15
    restartDelaySeconds = 5
    startupReadyTimeoutSeconds = 150
    startupFailureBackoffSeconds = 60
    runtimeDir = $runtimeDir
    logDir = $logDir
}
[IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))
Set-ExactPathAcl -Path $configPath -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Read

$binaryPath = '"' + $hostPath + '" "' + $PythonPath + '" "' + $supervisorPath + '" "' + $configPath + '" "' + $runtimeSid + '"'
if ($PSCmdlet.ShouldProcess($serviceName, 'Create and start Windows service')) {
    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existingService) {
        if ($existingService.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force; $existingService.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(40)) }
        Remove-ServiceRegistration $serviceName
    }
    New-Service -Name $serviceName -BinaryPathName $binaryPath -DisplayName 'OPPW Continuous Supervisor' `
        -Description 'Maintains configured OPPW account executor and publisher processes with global master/backup fencing.' `
        -StartupType Automatic | Out-Null
    Invoke-ScCommand @('config', $serviceName, 'start=', 'delayed-auto')
    Invoke-ScCommand @('failure', $serviceName, 'reset=', '86400', 'actions=', 'restart/5000/restart/15000/restart/30000')
    Start-Service -Name $serviceName
    (Get-Service -Name $serviceName).WaitForStatus('Running', [TimeSpan]::FromSeconds(40))
}
Write-Host "OPPW SERVICE INSTALLED role=$($NodeRole.ToUpperInvariant()) node=$nodeId config=$configPath"

[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $RepoRoot 'service\OPPWServiceHost.cs'
$compiler = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $compiler) { throw '.NET Framework C# compiler is required to build the Windows service host.' }
$destination = [IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
& $compiler /nologo /target:exe /optimize+ /reference:System.ServiceProcess.dll "/out:$destination" $source
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $destination -PathType Leaf)) {
    throw 'Windows service host compilation failed.'
}
Write-Host "SERVICE HOST BUILT path=$destination"

[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonPath = '',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
$versionFile = Join-Path $root 'VERSION'
if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) { throw 'VERSION is missing.' }
$version = (Get-Content -LiteralPath $versionFile -Raw).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must use MAJOR.MINOR.PATCH.' }

if ($PythonPath -eq '') {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { $pythonCommand = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $pythonCommand) { throw 'Python 3 is required. Pass -PythonPath when it is not on PATH.' }
    $PythonPath = $pythonCommand.Source
}

Push-Location $root
try {
    & git rev-parse --is-inside-work-tree | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Release root is not a Git repository.' }
    & git diff --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Release refused: unstaged tracked changes exist.' }
    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Release refused: staged but uncommitted changes exist.' }
    $untracked = @(& git ls-files --others --exclude-standard)
    if ($untracked.Count -gt 0) {
        throw "Release refused: untracked source files exist:`n$($untracked -join "`n")"
    }

    & $PythonPath (Join-Path $root 'tools\validate_source.py') --root $root
    if ($LASTEXITCODE -ne 0) { throw 'Canonical-source validation failed.' }

    & $PythonPath -m py_compile (Join-Path $root 'mt5\oppw_mt5_continuous.py')
    if ($LASTEXITCODE -ne 0) { throw 'MT5 Python compilation failed.' }
    & $PythonPath -m unittest discover -s (Join-Path $root 'mt5\tests') -p 'test_*.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'MT5 regression tests failed.' }
    & $PythonPath -m py_compile (Join-Path $root 'service\oppw_windows_supervisor.py')
    if ($LASTEXITCODE -ne 0) { throw 'Windows supervisor Python compilation failed.' }
    & $PythonPath -m unittest discover -s (Join-Path $root 'service\tests') -p 'test_*.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Windows supervisor regression tests failed.' }
    $serviceHostValidation = Join-Path ([IO.Path]::GetTempPath()) ('OPPWServiceHost-validation-' + [Guid]::NewGuid().ToString('N') + '.exe')
    try {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $root 'service\build-service-host.ps1') -RepoRoot $root -OutputPath $serviceHostValidation
        if ($LASTEXITCODE -ne 0) { throw 'Windows service host compilation failed.' }
    } finally {
        if (Test-Path -LiteralPath $serviceHostValidation) { Remove-Item -LiteralPath $serviceHostValidation -Force }
    }

    $php = Get-Command php -ErrorAction SilentlyContinue
    if (-not $php) { throw 'PHP CLI is required for release linting.' }
    $trackedPhp = @(& git ls-files 'Mobile/backend/*.php' 'Mobile/backend/**/*.php' | Sort-Object -Unique)
    foreach ($relative in $trackedPhp) {
        & $php.Source -l (Join-Path $root $relative) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "PHP lint failed: $relative" }
    }
    Write-Host "PHP VALIDATION PASSED files=$($trackedPhp.Count)"

    & (Join-Path $root 'tools\validate_mysql.ps1') -RepoRoot $root
    if ($LASTEXITCODE -ne 0) { throw 'Temporary-MySQL migration validation failed.' }

    & $PythonPath (Join-Path $root 'tools\validate_contracts.py') --root $root --php $php.Source
    if ($LASTEXITCODE -ne 0) { throw 'Cross-component contract validation failed.' }

    Push-Location (Join-Path $root 'Mobile')
    try {
        & .\gradlew.bat --no-daemon clean testDebugUnitTest assembleDebug
        if ($LASTEXITCODE -ne 0) { throw 'Android tests/build failed.' }
    } finally {
        Pop-Location
    }

    if ($ValidateOnly) {
        Write-Host "RELEASE VALIDATION PASSED version=$version"
        return
    }

    $dist = Join-Path $root 'dist'
    New-Item -ItemType Directory -Path $dist -Force | Out-Null
    $tempBase = Join-Path ([IO.Path]::GetTempPath()) ('oppw-release-' + [Guid]::NewGuid().ToString('N'))
    $stage = Join-Path $tempBase ("OPPW-$version")
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    try {
        $tracked = @(& git ls-files)
        $selected = $tracked | Where-Object {
            $_ -in @('VERSION','README.md','AGENTS.md','requirements_mt5','.github/pull_request_template.md') -or
            $_ -like 'docs/*' -or
            $_ -like 'contracts/*' -or
            $_ -like 'service/*' -or
            $_ -in @(
                'mt5/oppw_mt5_continuous.py','mt5/oppw_mt5_config.example.py',
                'mt5/README.md'
            ) -or
            $_ -like 'mt5/tests/*' -or
            $_ -like 'Mobile/app/src/*' -or
            $_ -like 'Mobile/backend/*' -or
            $_ -like 'Mobile/gradle/*' -or
            $_ -in @(
                'Mobile/build.gradle.kts','Mobile/settings.gradle.kts','Mobile/gradle.properties',
                'Mobile/gradlew','Mobile/gradlew.bat','Mobile/local.properties.example','Mobile/README.md'
            ) -or
            $_ -in @(
                'tools/release.ps1','tools/validate_source.py','tools/validate_mysql.ps1',
                'tools/validate_contracts.py'
            )
        }
        $selected = $selected | Where-Object {
            $_ -notlike 'Mobile/backend/private/*' -and
            $_ -ne 'Mobile/backend/config.php' -and
            $_ -notmatch '\.(bak|diff)$'
        }
        foreach ($relative in $selected) {
            $source = Join-Path $root $relative
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Tracked release source missing: $relative" }
            $destination = Join-Path $stage $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination -Force
        }

        $apk = Join-Path $root 'Mobile\app\build\outputs\apk\debug\app-debug.apk'
        if (-not (Test-Path -LiteralPath $apk -PathType Leaf)) { throw 'Android APK was not produced.' }
        $artifactDir = Join-Path $stage 'artifacts'
        New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
        Copy-Item -LiteralPath $apk -Destination (Join-Path $artifactDir "OPPW-Monitor-$version-debug.apk") -Force
        & powershell -ExecutionPolicy Bypass -File (Join-Path $root 'service\build-service-host.ps1') `
            -RepoRoot $root -OutputPath (Join-Path $artifactDir 'OPPWServiceHost.exe')
        if ($LASTEXITCODE -ne 0) { throw 'Release Windows service host compilation failed.' }

        $manifestPath = Join-Path $stage 'RELEASE-MANIFEST.sha256'
        $manifest = Get-ChildItem -LiteralPath $stage -Recurse -File |
            Where-Object { $_.FullName -ne $manifestPath } |
            Sort-Object FullName |
            ForEach-Object {
                $relative = $_.FullName.Substring($stage.Length + 1).Replace('\','/')
                $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                "$hash  $relative"
            }
        [IO.File]::WriteAllLines($manifestPath, [string[]]$manifest)

        $zip = Join-Path $dist "OPPW-$version.zip"
        $checksum = "$zip.sha256"
        if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
        if (Test-Path -LiteralPath $checksum) { Remove-Item -LiteralPath $checksum -Force }
        Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
        $zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        [IO.File]::WriteAllText($checksum, "$zipHash  OPPW-$version.zip`r`n")
        Write-Host "RELEASE CREATED version=$version archive=$zip sha256=$zipHash files=$($manifest.Count)"
    } finally {
        $resolvedTemp = [IO.Path]::GetFullPath($tempBase)
        if ($resolvedTemp.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath())) -and (Test-Path -LiteralPath $resolvedTemp)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
} finally {
    Pop-Location
}

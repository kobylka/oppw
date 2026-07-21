param(
    [Parameter(Mandatory = $false)]
    [string]$RepoRoot = "D:\oppw"
)

$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resolvedRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).ProviderPath

$files = @(
    "Mobile\app\build.gradle.kts",
    "Mobile\app\src\main\java\com\oppw\monitor\data\Models.kt",
    "Mobile\app\src\main\java\com\oppw\monitor\data\JsonParser.kt",
    "Mobile\app\src\main\java\com\oppw\monitor\ui\screens\PositionScreen.kt"
)

foreach ($relative in $files) {
    $source = Join-Path $packageRoot $relative
    $target = Join-Path $resolvedRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing package source: $source"
    }
    $parent = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    Write-Host "Installed $target"
}

Write-Host "OPPW Monitor v14.3.1 source installed."
Write-Host "Build with: D:\oppw\Mobile\gradlew.bat :app:assembleDebug"


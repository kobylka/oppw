$ErrorActionPreference = "Stop"
$version = "9.4.1"
$base = "https://services.gradle.org/distributions"
$distributionSha256 = "2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb"
$wrapperSha256 = "55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c"
$jarPath = Join-Path $PSScriptRoot "gradle\wrapper\gradle-wrapper.jar"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("oppw-gradle-wrapper-" + [Guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $zipPath = Join-Path $tempRoot "gradle-$version-bin.zip"
    Invoke-WebRequest "$base/gradle-$version-bin.zip" -OutFile $zipPath
    $actualDistribution = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualDistribution -ne $distributionSha256) { throw "Gradle distribution checksum mismatch" }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $tempRoot

    $project = Join-Path $tempRoot "wrapper-project"
    New-Item -ItemType Directory -Path $project | Out-Null
    New-Item -ItemType File -Path (Join-Path $project "settings.gradle") | Out-Null
    $gradle = Join-Path $tempRoot "gradle-$version\bin\gradle.bat"
    & $gradle --no-daemon -p $project wrapper --gradle-version $version --distribution-type bin --gradle-distribution-sha256-sum $distributionSha256
    if ($LASTEXITCODE -ne 0) { throw "Gradle failed to generate its official wrapper" }

    $generatedJar = Join-Path $project "gradle\wrapper\gradle-wrapper.jar"
    $actualWrapper = (Get-FileHash $generatedJar -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualWrapper -ne $wrapperSha256) { throw "Gradle wrapper checksum mismatch" }
    New-Item -ItemType Directory -Force (Split-Path $jarPath) | Out-Null
    Copy-Item -LiteralPath $generatedJar -Destination $jarPath -Force
} finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
Write-Host "Official Gradle $version wrapper installed: $jarPath"

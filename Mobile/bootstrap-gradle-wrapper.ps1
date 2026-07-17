$ErrorActionPreference = "Stop"
$version = "9.4.1"
$base = "https://services.gradle.org/distributions"
$jarPath = Join-Path $PSScriptRoot "gradle\wrapper\gradle-wrapper.jar"
$checksumPath = "$jarPath.sha256"
New-Item -ItemType Directory -Force (Split-Path $jarPath) | Out-Null
Invoke-WebRequest "$base/gradle-$version-wrapper.jar" -OutFile $jarPath
Invoke-WebRequest "$base/gradle-$version-wrapper.jar.sha256" -OutFile $checksumPath
$expected = (Get-Content $checksumPath -Raw).Trim().ToLowerInvariant()
$actual = (Get-FileHash $jarPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    Remove-Item $jarPath -Force
    throw "Gradle wrapper checksum mismatch"
}
Remove-Item $checksumPath -Force
Write-Host "Official Gradle $version wrapper installed: $jarPath"

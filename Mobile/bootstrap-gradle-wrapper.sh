#!/usr/bin/env sh
set -eu
VERSION=9.4.1
BASE=https://services.gradle.org/distributions
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
JAR="$ROOT/gradle/wrapper/gradle-wrapper.jar"
mkdir -p "$(dirname "$JAR")"
curl -fsSL "$BASE/gradle-$VERSION-wrapper.jar" -o "$JAR"
EXPECTED=$(curl -fsSL "$BASE/gradle-$VERSION-wrapper.jar.sha256" | tr -d '[:space:]')
ACTUAL=$(sha256sum "$JAR" | awk '{print $1}')
if [ "$ACTUAL" != "$EXPECTED" ]; then
  rm -f "$JAR"
  echo "Gradle wrapper checksum mismatch" >&2
  exit 1
fi
echo "Official Gradle $VERSION wrapper installed: $JAR"

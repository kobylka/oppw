#!/usr/bin/env sh
set -eu
VERSION=9.4.1
BASE=https://services.gradle.org/distributions
DISTRIBUTION_SHA256=2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb
WRAPPER_SHA256=55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
JAR="$ROOT/gradle/wrapper/gradle-wrapper.jar"
TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/oppw-gradle-wrapper.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM
ZIP="$TEMP_ROOT/gradle-$VERSION-bin.zip"
curl -fsSL "$BASE/gradle-$VERSION-bin.zip" -o "$ZIP"
printf '%s  %s\n' "$DISTRIBUTION_SHA256" "$ZIP" | sha256sum -c -
unzip -q "$ZIP" -d "$TEMP_ROOT"
PROJECT="$TEMP_ROOT/wrapper-project"
mkdir -p "$PROJECT"
: > "$PROJECT/settings.gradle"
"$TEMP_ROOT/gradle-$VERSION/bin/gradle" --no-daemon -p "$PROJECT" wrapper \
  --gradle-version "$VERSION" --distribution-type bin \
  --gradle-distribution-sha256-sum "$DISTRIBUTION_SHA256"
GENERATED="$PROJECT/gradle/wrapper/gradle-wrapper.jar"
printf '%s  %s\n' "$WRAPPER_SHA256" "$GENERATED" | sha256sum -c -
mkdir -p "$(dirname "$JAR")"
cp "$GENERATED" "$JAR"
echo "Official Gradle $VERSION wrapper installed: $JAR"

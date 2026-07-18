# OPPW Monitor Android v11 validation

Completed in the packaging environment:

- All Android manifest and resource XML files parse successfully.
- Lightweight Kotlin lexical validation passed for all 35 Kotlin source files.
- `PotentialPosition` exists in the model and is wired into every `MonitorSnapshot` construction.
- The JSON parser accepts both `potentialPosition` and `potential_position` plus camelCase/snake_case field variants.
- The Position screen contains all required flat-preview fields.
- Effective leverage is recalculated as `required deposit / balance`; a unit test covers the formula and fallback behavior.
- The example v41 payload is valid JSON and its published effective-leverage value matches the formula.
- `RowColumnParentData` is not referenced.
- The v9.1 authentication files are byte-identical to v10.1.1.
- Application ID remains `com.oppw.monitor`.
- Version is `11.0.0` with version code `15`.
- No credentials were added.

A full Gradle/Android compilation could not be run in this environment because Android SDK 37 and the Gradle distribution/dependencies are not cached, and outbound access to `services.gradle.org` is unavailable. Build with Android Studio and JDK 17 before installation.

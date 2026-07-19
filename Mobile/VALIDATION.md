# Validation

Completed:

- Python v44 compiles with `py_compile`.
- Unit test verifies that a requested `-62.5%` account loss is moved to exactly `-50%` in a linear MT5 profit model.
- Unit test verifies that a safer requested stop remains unchanged.
- Unit test verifies effective leverage uses the strategy multiplier `20`, not broker leverage `100`.
- Unit test verifies a stored `-0.5%` publisher-labeled trade takes priority over a zero MT5-history result.
- Kotlin `Models.kt` and `Formatters.kt` compile with Kotlin/JVM.
- Android model/parser field mapping for `accountLossCapApplied` is present.
- Android hard-stop formula text was removed.
- Android version is `12.3.0`, code `21`.

A full APK build was not run because the active environment has no Android SDK/Compose dependency cache.

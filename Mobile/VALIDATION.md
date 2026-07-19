# OPPW v12 validation

Completed in the packaging environment:

- Python v43 and the Android patch utility pass `py_compile`.
- MT5 pure-logic tests pass for all A/B/C/D boundaries and priority.
- Stop formula tests pass: 8x = -6.25%, 10x = -5.00%.
- What-if scenarios de-duplicate a hard stop that equals another scenario.
- Strategy decision IDs remain stable for identical inputs.
- PHP analytics passes `php -l`.
- PHP tests verify annualized Sharpe/Sortino with two returns, positive-only Sortino infinity and zero-variance Sharpe behavior.
- Android patch applies successfully to a representative v11 model/parser project.
- Patched Kotlin and overlay files pass delimiter/string-state validation.
- Analytics overlay explicitly sorts returns descending and labels the chart best-to-worst.
- No private configuration or credential is included.

A full Android APK build was not possible in this environment because the complete v11 Android project, Android SDK and its downloaded Gradle dependency cache were not available in the active runtime. Build the patched project in Android Studio/JDK 17 before installation.

A live MT5 broker connection and production MySQL migration were not executed. The MT5 file was syntax-compiled and its pure calculations were exercised with deterministic stubs; the SQL migration should first be run against a database backup.

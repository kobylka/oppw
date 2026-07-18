# OPPW Monitor v8 validation

- All PHP files pass `php -l`.
- MT5 v35 and the generic latest MT5 script pass Python bytecode compilation.
- Example payload is valid JSON.
- Gradle Wrapper JAR is included in the project.
- v8 requires the existing v7 database schema and no new migration.
- Full Android compilation must still be run in Android Studio because this environment has no Android SDK.

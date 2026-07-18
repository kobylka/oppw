# OPPW Monitor v9 validation

Validation performed in the packaging environment:

- All PHP files pass `php -l`.
- MT5 v38 and the generic current MT5 script pass Python bytecode compilation.
- Android XML files parse successfully.
- JSON example payload parses successfully.
- Pure Kotlin models, sample data, and formatters compile with Kotlin/JVM.
- The official Gradle Wrapper JAR remains included.
- No database schema change is required after v7.
- No private credentials are included in the package.

A complete Android Gradle build must still be run in Android Studio because the packaging environment does not include an Android SDK.

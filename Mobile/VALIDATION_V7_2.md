# OPPW Monitor v7.2 validation

- Removed `android.permission.USE_BIOMETRIC`.
- Removed the AndroidX Biometric dependency.
- Removed `BiometricAuthenticator.kt`.
- Removed the Real-account lock screen and all foreground/background relock logic.
- Removed biometric fields from `UiState`.
- Real and Demo account selection now follows the same paired-device HTTPS authorization path.
- Background stale-status checks now run for either selected account.
- Kotlin delimiter checks passed for every modified source file.
- Android XML parsing passed.
- No backend, database, MT5 strategy, publisher, authentication-token, notification, analytics, or log-paging logic changed.

A complete Android Gradle build must be run in Android Studio because the execution environment does not include the Android SDK.

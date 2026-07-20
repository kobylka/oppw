# OPPW Monitor 13.4 validation

- Android `compileDebugKotlin`: passed.
- Android unit tests: passed.
- Android `assembleDebug`: passed.
- Gradle version: 9.4.1.
- Backend change reviewed against `DATETIME(3)` storage and the full-precision `event_at` values retained in event JSON.
- No database schema or MT5 trading-strategy change is required.

PHP CLI is not installed on this workstation, so run `php -l` on the three backend files before production upload.

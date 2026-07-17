# Validation report

Performed in the generation environment:

- All PHP files pass `php -l` with PHP 8.4.
- The Python publisher passes `python -m py_compile`.
- Every Android XML file parses successfully.
- Pure Kotlin authentication/data models compile with `kotlinc`.
- Static checks confirm:
  - no `BuildConfig.API_TOKEN` remains;
  - no permanent mobile read token is present;
  - no direct `layout.weight` import remains;
  - the logs icon uses `Icons.AutoMirrored.Outlined.ListAlt`;
  - `local.properties` and `backend/config.php` are ignored by Git;
  - cleartext Android traffic is disabled;
  - Android backups are disabled for the app.

Not performed here:

- A full Gradle Android build, because this environment does not contain the Android SDK or downloaded Android/Compose dependencies.
- Live MySQL integration tests, because no MySQL server is installed in this environment.
- End-to-end HTTPS testing against a deployed domain and certificate.

Before production, run:

```powershell
.\gradlew.bat clean test assembleDebug
```

Then complete the pairing, refresh, revocation and account-authorization checks in `DEPLOYMENT_CHECKLIST.md`.

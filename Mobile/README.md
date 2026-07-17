# OPPW Monitor Android — multi-account edition

Read-only Android monitor for one or more OPPW strategy accounts. The phone never connects directly to MySQL and contains no trading functions.

## Compatibility

- Android `minSdk = 26` (Android 8.0 or newer).
- The Samsung Galaxy A53 is supported.
- The app is a universal Android APK; no device-specific native library is used.
- Internet access and an HTTPS API URL are required.

## Account switching

The app loads enabled accounts from `accounts.php`, displays the current account in the top bar, and opens an account selector from the wallet icon. The selected account is stored in Android SharedPreferences and restored after the app restarts.

The database starts with:

- `REAL` — Real account, default.
- `DEMO` — Demo account.

Add any number of accounts:

```sql
INSERT INTO monitor_accounts(account_key, display_name, account_type, broker_account_id, enabled, sort_order)
VALUES ('REAL_2', 'Second real account', 'REAL', '12345678', TRUE, 30);
```

Disable without deleting history:

```sql
UPDATE monitor_accounts SET enabled = FALSE WHERE account_key = 'REAL_2';
```

## Fresh installation

1. Create the MySQL user/database.
2. Import `backend/sql/schema.sql`.
3. Upload the contents of `backend/` to an HTTPS directory.
4. Copy `backend/config.example.php` to `backend/config.php` and fill in credentials/tokens.
5. Test:

```bash
curl https://monitor.example.com/oppw-api/health.php
curl https://monitor.example.com/oppw-api/accounts.php -H "Authorization: Bearer READ_TOKEN"
```

## Upgrade from the previous single-account deployment

1. Back up MySQL.
2. Import `backend/sql/migrate_multi_account.sql`.
3. Register every existing `strategy_key` in `monitor_accounts` before adding optional foreign keys.
4. Replace `accounts.php`, `status.php`, and `ingest.php` on the server.
5. Update `config.php` to include:

```php
'default_account_key' => 'REAL',
```

## Publishing Real and Demo

Run one publisher/strategy instance per account, with a different account key:

```powershell
# Real strategy machine/process
$env:OPPW_MONITOR_ACCOUNT_KEY = "REAL"

# Demo strategy machine/process
$env:OPPW_MONITOR_ACCOUNT_KEY = "DEMO"
```

Both may use the same ingest URL and write token:

```powershell
$env:OPPW_MONITOR_INGEST_URL = "https://monitor.example.com/oppw-api/ingest.php"
$env:OPPW_MONITOR_WRITE_TOKEN = "WRITE_TOKEN"
```

The JSON request contains `accountKey`, so snapshots and events remain separated in MySQL.

## Android configuration

Copy:

```powershell
Copy-Item .\local.properties.example .\local.properties
```

Set:

```properties
sdk.dir=C\:\\Users\\YOUR_NAME\\AppData\\Local\\Android\\Sdk
OPPW_API_BASE_URL=https://monitor.example.com/oppw-api/
OPPW_API_TOKEN=YOUR_READ_TOKEN
```

Open the project in Android Studio with JDK 17 and install Android SDK 37 when prompted.

## Build and install on Galaxy A53

Enable Developer options and USB debugging on the phone, connect USB, then:

```powershell
.\gradlew.bat assembleDebug
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Or copy the APK to the phone and open it after permitting installation from that source.

## API endpoints

- `GET accounts.php` — list enabled accounts and latest health.
- `GET status.php?account=REAL` — selected account snapshot and events.
- `POST ingest.php` — upload a snapshot under `accountKey`.
- `GET health.php` — API/database health.

## Security

- Android contains only the read token.
- The write token stays on the strategy machine.
- MySQL credentials stay only in server-side `config.php`.
- Use HTTPS only.
- Do not commit `local.properties` or `backend/config.php`.

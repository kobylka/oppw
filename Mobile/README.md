# OPPW Monitor — authenticated Android client and HTTPS API

A read-only Android monitoring application for OPPW strategy status. It supports Real, Demo and additional accounts, but contains no trade execution functionality.

## Architecture

```text
MT5 strategy -- HTTPS + write token --> ingest.php --> MySQL
Android app  -- HTTPS + device token --> accounts/status API --> MySQL
```

The writer and reader credentials are different. The Android app contains no permanent API key.

## Requirements

### Android development

- Android Studio with JDK 17
- Android SDK matching `compileSdk` in `app/build.gradle.kts`
- Android 8.0/API 26 or newer device

### Server

- HTTPS domain with a valid public certificate
- PHP 8.2 or newer
- PDO MySQL extension
- MySQL 8 or compatible MariaDB version with JSON and `DATETIME(3)` support
- Shell/SSH access for creating pairing codes and revoking devices

## 1. Database

For a new installation:

```bash
mysql -u root -p < backend/sql/schema.sql
```

For an existing multi-account OPPW database:

```bash
mysql -u root -p oppw_monitor < backend/sql/migrate_auth.sql
```

Create a restricted database user. The API needs `SELECT`, `INSERT`, `UPDATE` and `DELETE` on `oppw_monitor.*`.

## 2. Server configuration

Upload the contents of `backend/` to the API directory, for example `/var/www/oppw-api`.

Create the private configuration. The safest deployment stores it outside the document root:

```bash
cp /var/www/oppw-api/config.example.php /etc/oppw-monitor-config.php
export OPPW_MONITOR_CONFIG=/etc/oppw-monitor-config.php
```

Alternatively, place it at `backend/config.php`; the included web-server rules deny direct access.

Generate four independent secrets:

```bash
php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
```

Use them for:

```php
'write_token' => 'FIRST_VALUE',
'token_hmac_secret' => 'SECOND_VALUE',
'pairing_hmac_secret' => 'THIRD_VALUE',
'rate_limit_hmac_secret' => 'FOURTH_VALUE',
```

Set the database password and keep `config.php` outside Git.

## 3. HTTPS web server

Examples are included:

- `backend/apache-vhost.example.conf`
- `backend/nginx.example.conf`

The production API must use HTTPS. The PHP code also rejects non-HTTPS requests. Set `trust_forwarded_proto=true` only when a trusted reverse proxy overwrites `X-Forwarded-Proto`.

Verify:

```bash
curl https://monitor.example.com/oppw-api/health.php
```

Expected response:

```json
{"ok":true,"service":"oppw-monitor-api","time":"..."}
```

Verify that private paths are not accessible:

```bash
curl -I https://monitor.example.com/oppw-api/config.php
curl -I https://monitor.example.com/oppw-api/admin/list_devices.php
```

Both should return 403 or 404.

## 4. MT5 publishing

Configure v32 or later with the separate writer credential:

```powershell
$env:OPPW_MONITOR_INGEST_URL = "https://monitor.example.com/oppw-api/ingest.php"
$env:OPPW_MONITOR_WRITE_TOKEN = "WRITE_TOKEN_FROM_CONFIG"
$env:OPPW_MONITOR_ACCOUNT_KEY = "DEMO"
```

Do not use the writer token in Android.

## 5. Android configuration

Copy:

```powershell
Copy-Item .\local.properties.example .\local.properties
```

Set:

```properties
sdk.dir=C\:\\Users\\YOUR_NAME\\AppData\\Local\\Android\\Sdk
OPPW_API_BASE_URL=https://monitor.example.com/oppw-api/
```

There is no Android API token setting.

Open the project in Android Studio, select JDK 17, sync Gradle and run it on the emulator or Samsung A53.

## 6. Pair the Samsung A53

On the server:

```bash
cd /var/www/oppw-api
php admin/create_pairing_code.php --accounts=REAL,DEMO --minutes=10 --label=Samsung-A53
```

Example output:

```text
Pairing code: ABCD-EFGH-JKLM
Accounts: REAL, DEMO
Expires: 2026-07-17T13:45:00+00:00
```

Open the app, enter the code and press **Pair device**. The code can be used only once.

## 7. Add more accounts

Add the account to `monitor_accounts`, then create a new pairing code containing it:

```sql
INSERT INTO monitor_accounts(account_key, display_name, account_type, broker_account_id, enabled, sort_order)
VALUES ('REAL_2', 'Second real account', 'REAL', '12345678', TRUE, 30);
```

```bash
php admin/create_pairing_code.php --accounts=REAL,DEMO,REAL_2 --label=Samsung-A53
```

Change an existing device without re-pairing:

```bash
php admin/set_device_accounts.php --device=DEVICE_ID --accounts=REAL,DEMO,REAL_2
```

## 8. Device management

```bash
php admin/list_devices.php
php admin/revoke_device.php --device=DEVICE_ID
```

Schedule cleanup:

```cron
17 3 * * * cd /var/www/oppw-api && /usr/bin/php admin/cleanup.php >/dev/null 2>&1
```

## 9. Build APK

```powershell
.\bootstrap-gradle-wrapper.ps1
.\gradlew.bat clean assembleDebug
```

Debug APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

Production:

```text
Android Studio → Build → Generate Signed App Bundle or APK
```

## Security boundaries

Never put these in the APK or Git repository:

- MySQL username/password
- MT5 password
- `write_token`
- HMAC secrets
- raw production `config.php`
- signing keystore/password

The APK contains only the API base URL. Device credentials are issued after pairing and encrypted locally with Android Keystore.

# OPPW Monitor API deployment

The Android app must never connect directly to MySQL. This API is the only public layer:

- `ingest.php`: authenticated write endpoint used by the Python strategy/publisher.
- `status.php`: authenticated read endpoint used by Android.
- `health.php`: basic database health endpoint.

## Requirements

- PHP 8.2 or newer with PDO MySQL.
- MySQL 8.0 or MariaDB 10.6+.
- HTTPS certificate.
- Apache or Nginx.

## 1. Create database and user

```sql
CREATE DATABASE oppw_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'oppw_monitor'@'localhost' IDENTIFIED BY 'LONG_RANDOM_DB_PASSWORD';
GRANT SELECT, INSERT, DELETE ON oppw_monitor.* TO 'oppw_monitor'@'localhost';
FLUSH PRIVILEGES;
```

Import `sql/schema.sql`.

## 2. Configure API

Copy:

```bash
cp config.example.php config.php
```

Set database credentials, one read token, one different write token, and the strategy key. Generate tokens with:

```bash
php -r "echo bin2hex(random_bytes(32)), PHP_EOL;"
```

Place the API under an HTTPS URL such as:

```text
https://monitor.example.com/oppw-api/
```

Keep `config.php` outside the public web root when possible. If it must remain beside the scripts, the included Apache `.htaccess` blocks direct access. For Nginx, add:

```nginx
location ~ /(config|lib)\.php$ { deny all; }
```

## 3. Test

Health:

```bash
curl https://monitor.example.com/oppw-api/health.php
```

Upload the example snapshot:

```bash
curl -X POST https://monitor.example.com/oppw-api/ingest.php \
  -H "Authorization: Bearer WRITE_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @example_payload.json
```

Read it back:

```bash
curl https://monitor.example.com/oppw-api/status.php \
  -H "Authorization: Bearer READ_TOKEN"
```

## 4. Connect the strategy publisher

Set environment variables on the Windows machine running MT5:

```powershell
$env:OPPW_MONITOR_INGEST_URL = "https://monitor.example.com/oppw-api/ingest.php"
$env:OPPW_MONITOR_WRITE_TOKEN = "WRITE_TOKEN"
$env:OPPW_MONITOR_STRATEGY_KEY = "OPPW-001"
```

Import `StatusPublisher` from `publisher/oppw_status_publisher.py` and call `publish(snapshot, events)` after the strategy creates its minute status snapshot or an important event. Publishing is monitoring-only and must not block trade management; call it from a separate queue/thread and log failures locally.

## 5. Retention

Run daily:

```sql
DELETE FROM strategy_snapshots WHERE captured_at < UTC_TIMESTAMP() - INTERVAL 90 DAY;
DELETE FROM strategy_events WHERE event_time < UTC_TIMESTAMP() - INTERVAL 180 DAY;
```

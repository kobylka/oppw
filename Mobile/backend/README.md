# OPPW Monitor HTTPS API

This backend has two completely separate authentication paths:

- `ingest.php`: static **write-only publisher token**, used only by the MT5 strategy.
- Android read endpoints: **per-device pairing**, 15-minute access tokens, rotating refresh tokens, per-account permissions and remote revocation.

The Android app never receives the MySQL password, MT5 password, publisher token or a permanent shared read key.

## Public HTTPS endpoints

| Endpoint | Method | Authentication |
|---|---:|---|
| `health.php` | GET | none; returns only service health |
| `auth/pair.php` | POST | one-time pairing code |
| `auth/refresh.php` | POST | device ID + rotating refresh token |
| `auth/unpair.php` | POST | device access token |
| `auth/me.php` | GET | device access token |
| `accounts.php` | GET | device access token |
| `status.php?account=REAL` | GET | device access token + account permission |
| `ingest.php` | POST | publisher write token |

Do not expose `admin/`, `sql/`, `publisher/`, `config.php` or `lib.php` through the web server.

## CLI administration

```bash
php admin/create_pairing_code.php --accounts=REAL,DEMO --minutes=10 --label=Samsung-A53
php admin/list_devices.php
php admin/revoke_device.php --device=0123456789abcdef0123456789abcdef
php admin/set_device_accounts.php --device=0123456789abcdef0123456789abcdef --accounts=REAL,DEMO,REAL_2
php admin/cleanup.php
```

Run `cleanup.php` daily from cron.

# OPPW Monitor v7 HTTPS API

## Authentication paths

- `ingest.php`: MT5 write-only bearer token.
- Mobile read endpoints: paired-device access tokens, rotating refresh tokens, per-account authorization and revocation.
- `pairing-admin.php` and `push-admin.php`: optional browser administration protected by the separate pairing admin token and disabled by default.

## Public endpoints

| Endpoint | Method | Authentication |
|---|---:|---|
| `health.php` | GET | None |
| `auth/pair.php` | POST | One-time pairing code |
| `auth/refresh.php` | POST | Device refresh credential |
| `auth/unpair.php` | POST | Mobile bearer token |
| `accounts.php` | GET | Mobile bearer token |
| `status.php?account=DEMO` | GET | Mobile token + account grant |
| `events.php?account=DEMO` | GET | Mobile token + account grant |
| `analytics.php?account=DEMO` | GET | Mobile token + account grant |
| `push/register.php` | POST | Mobile bearer token |
| `push/unregister.php` | POST | Mobile bearer token |
| `ingest.php` | POST | MT5 writer token |
| `cashflow.php` | POST | MT5 writer token |

## v7 migrations

Fresh database: import `sql/schema.sql`.

Existing v6 database: import `sql/migrate_v7.sql` once.

## Log pagination

`events.php` uses an ID cursor:

```text
events.php?account=DEMO&limit=75&before_id=12345
```

Optional filters:

```text
buy_sell_only=1
event_name=POSITION_CLOSED
```

The transaction filter intentionally excludes `POSITION_OPEN`; it includes order-related BUY/SELL events and `POSITION_CLOSED`.

## Firebase push

Optional private config:

```php
'push_enabled' => true,
'firebase_project_id' => 'project-id',
'firebase_service_account_file' => '/private/path/service-account.json',
```

The service account file must remain outside the web root. Push failures never fail status ingestion; they are recorded in `monitor_push_tokens.last_error`.

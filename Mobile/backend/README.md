# OPPW Monitor v8 HTTPS API

## Authentication

- `ingest.php`: MT5 write-only bearer token.
- Mobile read endpoints: paired-device access tokens and per-account authorization.
- `pairing-admin.php` and `push-admin.php`: optional pairing-admin browser token.
- `market-admin.php` and `trade-admin.php`: optional manual-admin browser token.

## Endpoints

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
| `market-admin.php` | GET/POST | Manual browser admin token |
| `trade-admin.php` | GET/POST | Manual browser admin token |

## Database

Fresh database: import `sql/schema.sql`.

Existing v6 database: import `sql/migrate_v7.sql` once. v8 adds no columns or tables.

## Manual browser administration

Private config:

```php
'manual_admin_enabled' => false,
'manual_admin_token' => 'long-independent-random-token',
```

Enable only while importing data. Both pages require HTTPS, never put the token in the URL, apply IP-based rate limiting and return 404 while disabled.

`market-admin.php` writes two exchange-time markers for each supplied date: 09:30 ET open and 15:59 ET close. This makes weekly O/H/L/C work across DST changes.

`trade-admin.php` writes `strategy_trades` and optional daily equity points. It updates an existing record when account + ticket already exists.

## Log pagination

`events.php` uses an ID cursor and supports:

```text
events.php?account=DEMO&limit=75&before_id=12345
buy_sell_only=1
event_name=POSITION_CLOSED
```

`POSITION_IS_OPEN` is a state/check event, not a buy event. Historical `POSITION_OPEN` rows are normalized to `POSITION_IS_OPEN` by the API.


## v9 heartbeat and market aggregation

`status.php` derives the strategy heartbeat from the latest `strategy_snapshots.captured_at` value. A successful HTTP request does not make a stale publisher appear healthy. Flat Saturday/Sunday accounts return `WEEKEND IDLE`.

US100 current/previous-week and latest-day O/H/L/C are calculated only from `strategy_market_points`. The strategy week starts Friday at 15:30 Warsaw; the Friday open must exist between 15:30 and 15:35. Monday–Thursday opens use the earliest stored point of the day.

`events.php?hide_routine=1` hides `POSITION_OPEN`/`POSITION_IS_OPEN`, `ENTRY_SIGNAL_OPEN_AVAILABLE`, `EXIT_LATCH_CLEAR`, `OH`, `CH`, and any event whose name starts with `TSL`.

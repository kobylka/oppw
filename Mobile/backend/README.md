# OPPW Monitor v8 HTTPS API

## Authentication

- `ingest.php`: MT5 write-only bearer token.
- Mobile read endpoints: paired-device access tokens and per-account authorization.
- `pairing-admin.php` and `push-admin.php`: optional pairing-admin browser token.
- `market-admin.php` and `trade-admin.php`: optional manual-admin browser token.

Paired-device tokens never write immutable strategy authority. `mobile-receipt.php` records only a diagnostic delivery acknowledgement; an explicit per-device grant is still required for service-control writes.

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

For a fresh database, apply every non-comment entry in `sql/migration-order.txt` from top to bottom. `schema.sql` is the base schema; the remaining files are required forward-only migrations.

For an existing database, apply only the listed migrations that have not already been applied, preserving their order. Never replay `schema.sql` or an already-applied migration. In particular, `migrate_v12_trade_classes.sql` must precede the v46 and later migrations because current analytics and trade projections require its persistent return/classification columns and triggers.

## Retention and recovery

Run `php admin/retention.php` for a dry-run report. Apply bounded archival and cleanup with `php admin/retention.php --apply --archive-dir=<encrypted-path-outside-web-root>`. Ordinary events are hot for 180 days and minute equity is hot for 400 days; exact gzip NDJSON archives are verified before deletion, and equity is rolled into `strategy_equity_daily` first. `EXECUTION_STAGE` events, authority ledgers, service-control audits, and all `strategy_market_points` minute OHLC rows remain online indefinitely.

The full policy, scheduling guidance, archive requirements, and recovery drill are in `docs/DATA_LIFECYCLE.md`. `tools/validate_backup_restore.ps1` uses only synthetic data and two disposable MySQL containers; production restore procedures must always target a new database.

## Manual browser administration

CLI pairing grants must state service-control authority explicitly:

```powershell
php admin/create_pairing_code.php --accounts=REAL,DEMO --can-control-service=1
php admin/set_device_accounts.php --device=DEVICE_ID --accounts=REAL,DEMO --can-control-service=1
```

`set_device_accounts.php` preserves the device's existing service-control grant when the option is omitted. Use `--can-control-service=0` to revoke it deliberately. `list_devices.php` displays the effective grant.

Private config:

```php
'manual_admin_enabled' => false,
'manual_admin_token' => 'long-independent-random-token',
```

Enable only while importing data. Both pages require HTTPS, never put the token in the URL, apply IP-based rate limiting and return 404 while disabled.
The manual token must be configured explicitly and must differ from the pairing-admin token; missing or reused credentials keep both manual-write pages unavailable. All browser-admin forms also reject cross-site POSTs and return restrictive no-store, CSP, framing, referrer, content-type, and permissions headers.

`market-admin.php` writes two exchange-time markers for each supplied date: 09:30 ET open and 15:59 ET close. This makes weekly O/H/L/C work across DST changes.

`trade-admin.php` writes `strategy_trades` and optional daily equity points. It updates an existing record when account + ticket already exists.

## Analytics resource limits

Analytics accepts any positive rolling-week request and an explicit `all_history=1` request for the complete available account history. The Android screen exposes this as **All history**. Resource protection comes from an eight-account scope limit, bounded trade/lifecycle materialization, per-device and per-IP request rates, one concurrent request per device, hot-minute retention with indefinite daily fallback, and SQL queries constrained to the requested or complete available date range.

Successful analytics responses also use a private, server-side, data-watermark-keyed cache. Authentication, authorization, rate limits, filter validation, and per-device single-flight protection still run for every request. The default TTL is 30 seconds (configuration accepts 1 through 120 seconds), and a new trade or latest equity observation changes the key immediately. A hit returns the exact JSON bytes produced by the original request; `X-OPPW-Analytics-Cache` reports `HIT`, `MISS`, or `BYPASS`, while `Cache-Control: no-store` continues to prohibit client/proxy storage.

Optional private config:

```php
'analytics_cache_ttl_seconds' => 30,
'analytics_cache_dir' => '', // Empty uses PHP's system temp directory.
```

If a directory is configured, use an absolute path outside the web root and grant access only to the PHP worker identity. Relative, web-root-contained, and symbolic-link paths are rejected. Cache files are size-bounded, HMAC integrity-checked, stored under hash-only names, and written with file locking. Cache I/O failure bypasses reuse and does not make analytics unavailable.

## Web-server deployment

Only the Nginx deployment example is maintained. It allowlists the canonical HTTP PHP endpoints and returns 404 for source, SQL, tests, configuration examples, publisher code, and documentation. There are no Apache or `.htaccess` deployment artifacts in this repository.

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

US100 previous-week and latest-day O/H/L/C are calculated from `strategy_market_points`. Current-week open, high, low, and close come from the canonical MT5 snapshot's M1 observation window, beginning at the first XNYS cash open or at a current-week manual position's opening timestamp. A manual fill is included in weekly open/high/low. The exact first-session cash-open M1 boundary remains a separate strategy reference; stored minute points continue to supply daily cards.

Mobile daily and weekly equity curves use `equity-periods.php`. On the week's first actual trading session, both curves begin at the published XNYS cash open (normally 15:30 Europe/Warsaw). If a manual position was opened earlier on that same first session, both begin at its exact opening timestamp. On later trading days the daily curve begins at local midnight while the weekly curve retains its first-session boundary. Strategy-managed and post-open manual positions do not move that boundary.

`events.php?hide_routine=1` hides `POSITION_OPEN`/`POSITION_IS_OPEN`, `ENTRY_SIGNAL_OPEN_AVAILABLE`, `EXIT_LATCH_CLEAR`, `OH`, `CH`, and any event whose name starts with `TSL`.

# OPPW Monitor v8 HTTPS API

## Authentication

- `ingest.php`: MT5 write-only bearer token.
- Mobile read endpoints: paired-device access tokens and per-account authorization.
- `pairing-admin.php` and `push-admin.php`: optional pairing-admin browser token.
- `market-admin.php` and `trade-admin.php`: optional manual-admin browser token.

Paired-device tokens never write immutable execution authority. `mobile-receipt.php` records only a diagnostic delivery acknowledgement; an explicit per-device operational-control grant is required for service desired-state writes and per-account entry-rule toggles. Globally fenced executors alone may record weekly entry-rule defer/skip transitions through `strategy-controls.php`.

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
| `strategy-decisions.php?account=DEMO` | GET | Mobile token + account grant |
| `strategy-specifications.php?account=DEMO` | GET | Mobile token + account grant |
| `strategy-controls.php?account=DEMO` | GET/POST | Mobile operational-control grant or fenced MT5 writer |
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

Run `php admin/retention.php` for a dry-run report. Apply bounded archival and cleanup with `php admin/retention.php --apply --archive-dir=<encrypted-path-outside-web-root>`. Ordinary events are hot for 180 days and minute equity is hot for 400 days; exact gzip NDJSON archives are verified before deletion, and equity is rolled into `strategy_equity_daily` first. `EXECUTION_STAGE` events, authority ledgers, service-control audits, entry-rule controls/audits, and all `strategy_market_points` minute OHLC rows remain online indefinitely.

The full policy, scheduling guidance, archive requirements, and recovery drill are in `docs/DATA_LIFECYCLE.md`. `tools/validate_backup_restore.ps1` uses only synthetic data and two disposable MySQL containers; production restore procedures must always target a new database.

## Manual browser administration

The ordered account migration preserves keys `DEMO` and `REAL` while labeling them `DEMO BOSSA` and `REAL BOSSA`. It also creates `DEMO_TMS` and `REAL_TMS` disabled. After both nodes have populated TMS private files, register them to enable the accounts and initialize their service desired state and entry-rule controls:

```powershell
php admin/register_account.php --account=DEMO_TMS --type=DEMO --display-name="DEMO TMS" --broker-account-id=123456 --sort-order=40
php admin/register_account.php --account=REAL_TMS --type=REAL --display-name="REAL TMS" --broker-account-id=654321 --sort-order=30
```

Account keys are the stable identifiers used by MT5, service control, Mobile grants, leases, audit records, and analytics. They must match the supervisor's configured list.

CLI pairing grants must state operational-control authority explicitly. The existing `can_control_service` grant covers both service desired state and entry-rule toggles:

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

Analytics accepts any positive rolling-week request and an explicit `all_history=1` request for the complete available account history. Numeric windows default to the latest observations; `window_end_date=YYYY-MM-DD` moves the same fixed N-week duration to end after that inclusive Europe/Warsaw date. The Android screen exposes a bounded date picker and **All history**. Resource protection comes from an eight-account scope limit, bounded trade/lifecycle materialization, per-device and per-IP request rates, one concurrent request per device, hot-minute retention with indefinite daily fallback, and SQL queries constrained to the requested or complete available date range.

Successful analytics responses also use a private, server-side, data-watermark-keyed cache. Authentication, authorization, rate limits, filter validation, and per-device single-flight protection still run for every request. The default TTL is 30 seconds (configuration accepts 1 through 120 seconds), and a new trade or latest equity observation changes the key immediately. A hit returns the exact JSON bytes produced by the original request; `X-OPPW-Analytics-Cache` reports `HIT`, `MISS`, or `BYPASS`, while `Cache-Control: no-store` continues to prohibit client/proxy storage.

When the whole-response cache misses, analytics reuses raw input segments for completed Europe/Warsaw weeks. Only the latest requested week (including the actual current week when present) is queried live, so frequent minute-equity publication no longer forces a full historical MySQL scan. Completed segments are shared only across the same database, account scope, dataset, and applicable trade filters. Their default TTL is 24 hours (configuration accepts 5 minutes through 30 days), which bounds how long a late correction to an older completed week can remain cached. `X-OPPW-Analytics-Segments` reports historical hits/misses and live-query row counts for deployment diagnostics. A lightweight streaming reducer derives only the daily first/low/close and trade-episode refinement state consumed by the response; it does not build the discarded full minute chart. The endpoint preserves the existing response contract.

Optional private config:

```php
'analytics_cache_ttl_seconds' => 30,
'analytics_segment_cache_ttl_seconds' => 86400,
'analytics_cache_dir' => '', // Empty uses PHP's system temp directory.
```

If a directory is configured, use an absolute path outside the web root and grant access only to the PHP worker identity. Relative, web-root-contained, and symbolic-link paths are rejected. Cache files are size-bounded, HMAC integrity-checked, stored under hash-only names, and written with file locking. Cache I/O failure bypasses reuse and does not make analytics unavailable.

## Web-server deployment

Web-server configuration is deployment-owned and no Apache, Nginx, or `.htaccess` example is committed. The deployed document root or explicit route allowlist must make only the canonical HTTP endpoints reachable and must deny source, SQL, tests, configuration examples, publisher code, and documentation. Preserve HTTPS and the security headers emitted by PHP; validate the actual server configuration rather than assuming a repository example is active.

## Push token cache

When `push_enabled` is true, configure `fcm_cache_dir` as an absolute dedicated directory outside the web root. The PHP worker must own it and no group or other identity may access it on POSIX systems (mode `0700`; token files are `0600`). The backend rejects missing, relative, web-root-contained, symbolic-link, broadly permissioned, or unwritable paths. OAuth tokens never fall back to the shared system temporary directory.

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

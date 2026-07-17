# OPPW Monitor v7.2

Read-only Android monitor for the OPPW MetaTrader 5 strategy. The Android app never connects to MT5 or MySQL directly and contains no trading controls.

## Architecture

```text
MT5 v34 publisher -> HTTPS ingest.php -> MySQL <- authenticated HTTPS API <- Android v7.2
                                              -> Firebase Cloud Messaging
```

## v7.2 highlights

- Swipe navigation: Overview, Position, Analytics, Logs, Settings.
- Weekly market reference is the first regular-session open of the week, normally Monday or the next trading day after a holiday.
- Full current-week and previous-week O/H/L/C plus latest-day O/H/L/C.
- Local-time log display, with Android converting API timestamps to the phone timezone.
- Cursor-paged logs that load while scrolling. Android Paging retains at most 500 rows in memory.
- Server-side buy/sell filtering includes `BUY*`, `SELL*`, and `POSITION_CLOSED`; it does not classify `POSITION_OPEN` as a transaction.
- Bid/ask times display as `HH:mm:ss` without milliseconds.
- Mobile OH and CH targets share the entry-price target. On Friday both display `entry × 1.05`.
- FCM notifications for position opened/closed, broker protection loss, MT5 disconnects, and critical publisher events.
- Foreground and WorkManager stale-API notifications.
- Real and Demo accounts are both accessible after server pairing; no fingerprint or biometric hardware is required.
- Trade analytics: MFE, MAE, entry/exit slippage, duration, exit-reason results, weekly summaries, profit factor, expectancy, payoff ratio, capture efficiency, edge ratio, drawdown, recovery factor, consistency, streaks, and time in market.

## Upgrade from v6

1. Back up MySQL.
2. Import `backend/sql/migrate_v7.sql` once through phpMyAdmin.
3. Upload the complete `backend/` directory, preserving your private `config.php` or external configuration file.
4. Add the optional Firebase fields shown below.
5. Replace the strategy script with `mt5/oppw_mt5_continuous_v34.py`; keep your private `oppw_mt5_config.py`.
6. Replace the Android project source, preserve `local.properties`, and rebuild.

The migration must be run once. Re-running its `ALTER TABLE` statements will report duplicate columns or indexes.

## Backend configuration

Add to the private PHP configuration:

```php
'push_enabled' => true,
'firebase_project_id' => 'your-firebase-project-id',
'firebase_service_account_file' => '/private/path/firebase-service-account.json',
```

The service-account JSON must be outside the public document root and readable only by PHP. PHP requires cURL and OpenSSL for FCM HTTP v1.

When push is disabled or incomplete, all status, authentication, analytics, and log functions still work.

To test delivery without terminal access, temporarily enable the existing browser administration settings and open:

```text
https://your-domain.example/oppw-backend/push-admin.php
```

It uses the separate `pairing_admin_token`. Disable `pairing_admin_enabled` again after the test.

## Firebase Android configuration

Create a Firebase Android app with package:

```text
com.oppw.monitor
```

Set these public identifiers in `local.properties` without quotes:

```properties
OPPW_API_BASE_URL=https://your-domain.example/oppw-backend/
OPPW_FIREBASE_APPLICATION_ID=1:123456789:android:abcdef
OPPW_FIREBASE_PROJECT_ID=your-project-id
OPPW_FIREBASE_API_KEY=your-public-firebase-api-key
OPPW_FIREBASE_SENDER_ID=123456789
```

These Firebase Android identifiers are not database or MT5 secrets. Never put the PHP writer token, MySQL password, MT5 password, or Firebase service-account private key in the Android project.

## Build

```powershell
.\gradlew.bat --stop
.\gradlew.bat clean assembleDebug
```

If `gradle-wrapper.jar` is absent, `gradlew.bat` runs the included checksum-verified bootstrap script and downloads the official Gradle 9.4.1 wrapper automatically. Android Studio's bundled JBR is used when `JAVA_HOME` is not set.

APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

## Manual market history without a trade

`strategy_market_points` is independent of `strategy_trades`. Store timestamps in UTC. The first row whose `phase` contains `REGULAR` becomes the weekly open.

Example Monday opening marker and daily summary:

```sql
SET @account = 'DEMO';

INSERT INTO strategy_market_points(
    strategy_key, captured_minute, current_price, bid, ask,
    m1_open, m1_high, m1_low, m1_close, phase
) VALUES
(@account, '2026-07-13 13:30:00', 23000.00, NULL, NULL, 23000.00, 23000.00, 23000.00, 23000.00, 'REGULAR'),
(@account, '2026-07-13 19:59:00', 23100.00, NULL, NULL, 23000.00, 23200.00, 22800.00, 23100.00, 'REGULAR')
ON DUPLICATE KEY UPDATE
    current_price = VALUES(current_price),
    m1_open = VALUES(m1_open),
    m1_high = VALUES(m1_high),
    m1_low = VALUES(m1_low),
    m1_close = VALUES(m1_close),
    phase = VALUES(phase);
```

Insert one daily summary for every missing trading day. No position or trade row is required.

## Logs

`events.php` accepts:

```text
account=DEMO
limit=75
before_id=<oldest loaded id>
buy_sell_only=1
event_name=POSITION_CLOSED
```

Pages are returned newest first. The API also returns the total number of matching events. The app shows `loaded of total`, automatically requests older pages near the bottom, and discards distant pages once the 500-row cache limit is reached.

## Account access policy

Both Real and Demo accounts use the same paired-device HTTPS authorization. The app has no local biometric gate and works on phones without fingerprint or face authentication. Server-side per-account permissions remain enforced.

## Trade analytics data

The backend derives analytics from `strategy_trades`. The ingest endpoint:

- opens or updates a trade whenever a position snapshot exists;
- tracks best/worst observed price, MFE, MAE, maximum unrealized profit/drawdown;
- stores entry/exit reference prices and slippage when corresponding order-request events are available;
- closes the trade when the snapshot transitions from open to flat;
- stores the first observed balance and detects flat-account top-ups/withdrawals.

Metrics are only as granular as the publisher snapshot interval. With five-second snapshots, MFE and MAE are five-second sampled values, not tick-perfect values.

## MT5 integrity

v34 differs from v33 only in mobile publishing metadata:

- build/user-agent version;
- the displayed CH target now uses the same trade-entry target as OH.

Trading conditions, order execution, scheduling, sizing, SL/TP handling, recovery, and the continuous execution loop are unchanged.

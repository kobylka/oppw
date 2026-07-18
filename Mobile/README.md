# OPPW Monitor v8

Read-only Android monitor for the OPPW MetaTrader 5 strategy. The app never connects directly to MT5 or MySQL and contains no trading controls.

## Architecture

```text
MT5 v35 -> HTTPS ingest.php -> MySQL <- authenticated HTTPS API <- Android v8
                                    -> Firebase Cloud Messaging (optional)
```

## v8 changes

- Exposure is always shown as `MT5 margin/deposit × 20`.
- Effective leverage is recalculated as `(deposit × 20) / equity`.
- The all-time chart has dated x-axis labels and separate equity and cumulative-deposits lines.
- Protection/regime names are human-readable.
- OH is published and logged only while that day's scheduled open check is still pending. After it is checked, it disappears from All conditions and cannot remain the closest condition.
- The open-position summary shows the potential OH/CH exit target instead of the normally empty broker TP.
- The Logs transaction-filter description wraps correctly and the switch remains on screen.
- Health freshness now reads `Heartbeat: 5.5s`.
- `market-admin.php` imports a missing week of US100 O/H/L/C through a browser.
- `trade-admin.php` imports historical trades and optional balance points through a browser.

## Upgrade from v7

1. Back up MySQL.
2. Upload the complete v8 `backend/` directory while preserving private `config.php`.
3. No new database migration is required if `migrate_v7.sql` was already imported.
4. Replace the Python strategy with `mt5/oppw_mt5_continuous_v35.py`, preserving private `oppw_mt5_config.py`.
5. Replace the Android source, preserve `local.properties`, sync in Android Studio, and run.

## Manual history pages

Add these optional values to private `config.php`:

```php
'manual_admin_enabled' => true,
'manual_admin_token' => 'A_DIFFERENT_LONG_RANDOM_TOKEN',
```

Then open:

```text
https://your-domain.example/oppw-backend/market-admin.php
https://your-domain.example/oppw-backend/trade-admin.php
```

`market-admin.php`:

- defaults to the previous week;
- accepts Monday–Friday O/H/L/C;
- allows blank holidays;
- uses America/New_York 09:30 and 15:59 markers and converts them to UTC;
- upserts into `strategy_market_points` without requiring a trade.

`trade-admin.php`:

- accepts a real ticket or generates a synthetic historical ticket;
- stores open/close time, prices, profit, exit reason, volume, MFE, MAE and slippage;
- optionally inserts balance-before and balance-after points so the all-time equity curve includes the trade period.

Disable browser administration after use:

```php
'manual_admin_enabled' => false,
```

If the new manual settings are absent, the pages fall back to the existing pairing-admin enable flag and token for backward compatibility.

## All-time chart deposits

The green line is cumulative money deposited by date:

- initial balance;
- top-ups;
- positive manual adjustments.

Withdrawals do not reduce the historical “deposits to date” line.

## Firebase

Firebase remains optional and is used only for push notifications. Status, logs, charts, authentication and manual-history pages work with:

```php
'push_enabled' => false,
```

## Build

The standard Gradle Wrapper JAR is included. Android Studio can perform Gradle sync and build automatically. Command-line equivalent:

```powershell
.\gradlew.bat clean assembleDebug
```

APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

## MT5 execution change

v35 intentionally changes OH lifecycle reporting and evaluation state:

- OH is checked at the existing scheduled open-action time;
- after `last_open_action_date` is set for the day, OH is no longer included in mobile conditions, closest-condition status or minute condition reports;
- CH, TO, SL, TSL, BE, sizing, entry timing and order execution rules otherwise remain unchanged.

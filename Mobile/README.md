# OPPW Monitor v6

Read-only Android monitor for the OPPW MT5 strategy, with device pairing, multiple accounts, HTTPS authentication, MySQL history, trade records and equity charts.

## v6 changes

- Swipe left/right between Overview, Position, Logs and Settings.
- Unpair moved to Settings and protected by a confirmation dialog.
- Logs replace Checks & Logs.
- Data freshness ages advance every second instead of remaining frozen at the last payload value.
- Overview shows HTTPS retrieval age, strategy regime, actual weekday buy window, balance, effective leverage and effective P/L percentage.
- Current-week and previous-week US100 statistics are generated from stored minute snapshots.
- Separate daily, weekly and all-time equity curves.
- Position shows bid/ask timestamps and every condition supplied by the strategy publisher.
- Risk bar sorts SL, entry and current-price markers by their actual prices.
- Logs support a buy/sell-only switch and exact event-name filtering.
- Backend stores minute equity/market points, trades, initial balance and cash-flow adjustments.

## Components

- `app/` — Android Studio Kotlin/Jetpack Compose project.
- `backend/` — authenticated PHP/MySQL HTTPS API.
- `backend/sql/migrate_v6.sql` — v5-to-v6 database migration and history backfill.
- `mt5/oppw_mt5_continuous_v33.py` — publishing-only extension of v32.
- `mt5/oppw_mt5_config.example.py` — credential-free v32-compatible configuration template.

## Upgrade an existing deployment

### 1. Back up MySQL

Export the database through phpMyAdmin before changing the schema.

### 2. Run the migration in phpMyAdmin

Open the database, select **Import**, and import:

```text
backend/sql/migrate_v6.sql
```

The migration creates:

- `strategy_equity_points`
- `strategy_market_points`
- `strategy_trades`
- `account_cash_flows`

It also backfills equity and market minute history from existing `strategy_snapshots`.

### 3. Upload the backend

Upload the contents of `backend/` over the current backend, but keep your existing private `config.php` or `/etc/oppw-monitor-config.php`.

New endpoint:

```text
POST cashflow.php
```

It is protected by the MT5 publisher write token and is optional for manually recording a top-up or withdrawal.

### 4. Replace the MT5 publishing companion

Copy:

```text
mt5/oppw_mt5_continuous_v33.py
```

as your active `oppw_mt5_continuous.py`. Keep your private `oppw_mt5_config.py`; the package contains only `oppw_mt5_config.example.py`.

v33 changes only the mobile snapshot publishing methods. BUY, SELL, OH, CH, TO, SL, TSL, BE, sizing, recovery, scheduling and the continuous loop are unchanged from v32.

The publisher adds:

- tick price timestamps;
- current protection regime;
- weekday-specific buy-window label;
- all price conditions: SL/TSL, OH, CH and BE when armed.

### 5. Configure Android

`local.properties`:

```properties
sdk.dir=C\:\\Users\\YOUR_NAME\\AppData\\Local\\Android\\Sdk
OPPW_API_BASE_URL=https://your-domain.example/oppw-backend/
```

Do not use quotes around the URL.

### 6. Build

```powershell
.\gradlew.bat clean assembleDebug
```

APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

## Percentage definitions

- **P/L % effective** = current absolute P/L ÷ MT5 balance × 100.
- **Weekly low %** = weekly low relative to the first stored regular-session Friday open.
- **Daily low %** = latest trading-day low relative to that Friday open.
- **Minimum balance at 50% margin** = MT5 margin/deposit × 1.765.

Before Friday regular trading begins, Friday-open-based percentages are unavailable and the app displays `—`.

## Equity history

- Daily chart: previous 24 hours.
- Weekly chart: previous seven days.
- All-time chart: final stored equity point for each UTC day.

The backend uses `strategy_equity_points`, not a local phone cache, so all paired devices see the same history.

## Cash flows

The backend automatically records:

- the first observed balance as `INITIAL`;
- flat-account balance changes without trade events as `TOP_UP` or `WITHDRAWAL` with source `AUTO_DETECTED`.

A manual cash flow can be recorded with the write token:

```json
{
  "accountKey": "REAL",
  "type": "TOP_UP",
  "amount": 10000,
  "balanceAfter": 40000,
  "note": "Broker deposit"
}
```

Post it to `cashflow.php`. The Android app remains read-only.

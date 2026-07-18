# OPPW Monitor v9.1

Read-only Android monitor for the OPPW MetaTrader 5 strategy. The app never connects directly to MT5 or MySQL and contains no trading controls.

## Architecture

```text
MT5 v38 -> HTTPS ingest.php -> MySQL <- authenticated HTTPS API <- Android v9.1
                                    -> Firebase Cloud Messaging (optional)
```

## v9.1 corrections

- Health is now strictly price-based: `OK`, `UNKNOWN`, or `WARNING`.
- Overview shows the continuous-loop heartbeat age and exact last US100 tick timestamp separately.
- Cached Friday state is overridden locally on flat weekends; OH and all other scheduled checks are suppressed.
- Deposits-to-date is recovered from cash-flow `balance_after` or the earliest account balance when necessary and is drawn as a dashed step line.
- No database migration and no MT5 update are required from v9.

## v9 changes

- Every active condition is displayed in its own full condition card, using the same layout as Closest condition.
- Logs hide routine checks by default: `POSITION_IS_OPEN`, `ENTRY_SIGNAL_OPEN_AVAILABLE`, `EXIT_LATCH_CLEAR`, `OH`, `CH`, and all `TSL*` checks.
- New publishers emit `POSITION_IS_OPEN`; the API also renames historical `POSITION_OPEN` records when returning them.
- Analytics adds annualized Sharpe and Sortino plus Calmar, Omega, Ulcer Index, daily VaR 95%, and Expected Shortfall 95%.
- Risk metrics use daily equity returns adjusted for external cash flows so deposits and withdrawals do not become fake investment returns.
- Heartbeat is based on the latest snapshot written by the continuous MT5 loop. The app separately displays its state, elapsed age, and exact last-update time.
- A flat account on Saturday or Sunday reports `WEEKEND IDLE`, phase `Weekend`, and regime `None`, even when the latest stored payload was created on Friday.
- The all-time equity curve starts at the recorded initial funding date and includes exact cash-flow dates. The deposits-to-date line includes initial funding, top-ups, and positive adjustments.
- Current-week and previous-week US100 values are calculated only from `strategy_market_points`, independent of position entry data.
- The strategy market week starts Friday at the regular-session open. Friday open is accepted only from 15:30:00–15:35:00 Warsaw time; later Friday points do not silently replace it. Monday–Thursday daily opens use the first available point of the day.
- MT5 prints a centered bold AutoTrading banner after each minute Trade Status: green when enabled and red when disabled.

## Upgrade from v8

1. Back up MySQL.
2. Upload the complete v9 `backend/` directory while preserving private `config.php`.
3. No new tables or columns are required after the v7 schema.
4. Add this optional setting to private `config.php` or keep the default of 180 seconds:

```php
'monitor_heartbeat_stale_seconds' => 180,
'monitor_price_warning_seconds' => 60,
```

5. Replace the Python strategy with `mt5/oppw_mt5_continuous_v38.py`, preserving private `oppw_mt5_config.py`.
6. Replace the Android source while preserving `local.properties`.
7. Open the project in Android Studio, sync Gradle, and press Run.

## Analytics metrics

- **Sharpe ratio:** annualized mean daily capital-adjusted return divided by daily standard deviation; zero risk-free rate.
- **Sortino ratio:** annualized mean daily capital-adjusted return divided by downside deviation.
- **Calmar ratio:** annualized compounded return divided by maximum percentage drawdown.
- **Omega ratio:** sum of positive daily returns divided by the absolute sum of negative daily returns, using a 0% threshold.
- **Ulcer Index:** root-mean-square percentage drawdown from the running peak.
- **Daily VaR 95%:** empirical fifth-percentile daily loss.
- **Expected Shortfall 95%:** average daily loss among returns at or below the VaR threshold.

The screen shows the number of daily return observations. Metrics remain zero until enough history exists to calculate a nonzero denominator.

## Heartbeat semantics

`status.php` uses `strategy_snapshots.captured_at`, not the time of the successful HTTPS request:

- `RUNNING`: latest publisher update is within the configured threshold.
- `STALE`: the backend is reachable but the MT5 continuous loop has stopped updating it.
- `WEEKEND IDLE`: Saturday/Sunday, no open position, and the loop may intentionally be stopped.

The Overview screen shows both elapsed time since the publisher update and its exact timestamp.

## All-time deposits line

The deposits-to-date line is gross funded capital by date:

- `INITIAL`
- `TOP_UP`
- positive `ADJUSTMENT`

Withdrawals do not reduce this gross deposits line. Cash-flow dates are merged with equity dates. Before the first stored equity point, the curve uses `balance_after` or cumulative deposits so the chart begins at the initial funding date.

## US100 market-week rules

The current and previous market cards read only `strategy_market_points`:

- Friday regular-session open: first point from 15:30:00 through 15:35:00 Warsaw.
- Monday–Thursday daily open: earliest stored point of the calendar day, preferably the midnight point from the publisher or manual import.
- Weekly high/low/close and latest-day O/H/L/C: aggregated from stored market points.
- No position open price is used.

The browser importer `market-admin.php` now accepts a Friday-started strategy week: Friday plus Monday–Thursday.

## MT5 console banner

After each minute Trade Status, v38 prints only:

```text
2026-07-18 09:00:00 AUTOTRADING_ENABLED
```

or:

```text
2026-07-18 09:00:00 AUTOTRADING_DISABLED
```

It is centered and printed in bold high-intensity green/red. Standard terminals do not support changing font size for one individual line without changing the whole console, so v38 does not alter the terminal font size.

## Manual administration

The existing browser pages remain available when temporarily enabled:

```php
'manual_admin_enabled' => true,
'manual_admin_token' => 'A_DIFFERENT_LONG_RANDOM_TOKEN',
```

```text
https://your-domain.example/oppw-backend/market-admin.php
https://your-domain.example/oppw-backend/trade-admin.php
```

Disable browser administration after use.

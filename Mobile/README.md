# OPPW v12 full change set

This package upgrades the uploaded OPPW MT5 continuous-loop v41, the monitor backend analytics endpoint, and the Android v11 source.

## Implemented

### Pre-trade What-if ticket

While the account is flat, MT5 v43 publishes a structured `potentialPosition` object containing:

- proposed side, symbol, current MT5 BUY price and volume;
- MT5 `order_calc_margin` required deposit and its source;
- balance, equity, free margin before/after, margin usage and projected margin level;
- strategy leverage and effective leverage;
- proposed notional and sizing units;
- hard-stop price, cash loss and account return at the stop;
- scenarios for -0.5%, -1%, hard SL, -3% and -5% underlying moves.

The requested underlying hard-stop formula is:

```text
stop return = -0.5 / strategy leverage
8x  = -6.25%
10x = -5.00%
```

### Strategy decision recorder

MT5 publishes `strategyDecision` and emits `STRATEGY_DECISION_RECORDED` whenever a meaningful decision input changes. It records:

- stable decision ID;
- selected 8x/10x leverage and exact reason;
- previous completed-week return and source;
- previous closed-trade return and source;
- sizing, MT5 margin, effective leverage and hard-stop risk;
- publisher build and any calculation error.

The decision sources are recovered from MT5 market/deal history when possible and explicitly marked as state fallbacks otherwise.

### Annualized closed-trade Sharpe and Sortino

`backend/analytics.php` now uses closed-trade account returns only and annualizes with `sqrt(52)` because the strategy normally produces one observation per week.

- Minimum sample: 2 valid closed-trade returns, not 5.
- Sharpe uses sample standard deviation.
- Sortino uses a zero target and downside deviation across all observations.
- If all returns are positive, Sortino is displayed as `∞` instead of `N/A`.
- Sharpe remains mathematically undefined when all sampled returns are identical because volatility is zero.

### Guy Fleury A/B/C/D trade classes

Classification priority is fixed as:

1. **A:** pre-leverage return `>= +0.7%`.
2. **B:** pre-leverage return `>= 0%` and `< +0.7%`.
3. **C:** negative break-even or TSL exit.
4. **D:** every remaining trade, including negative TO/SL exits.

MT5 v43 includes `preleverage_return` and `trade_class` in every new `POSITION_CLOSED` publisher event. The database migration adds persistent columns, backfills historical trades and installs insert/update triggers so manual and publisher-created records are classified consistently.

### Best-to-worst trade graph

Analytics returns every closed trade sorted by pre-leverage return descending. Android defensively sorts it again and renders:

```text
left = best trade  ->  right = worst trade
```

The chart includes a zero line, mean-return line and A/B/C/D-colored points.

## Package contents

```text
mt5/oppw_mt5_continuous_v43.py
mt5/oppw_mt5_v41_to_v43.diff
backend/analytics.php
backend/sql/migrate_v12_trade_classes.sql
android_patch/apply_v12_patch.py
android_patch/AnalyticsScreen.kt
android_patch/PositionScreen.kt
docs/example_v43_flat_snapshot.json
tests/
```

No account configuration, password, write token, Firebase secret or other private credential is included.

## Deployment order

1. Back up the OPPW database.
2. Run `backend/sql/migrate_v12_trade_classes.sql` once.
3. Upload `backend/analytics.php` over the existing analytics endpoint. Preserve the existing private `lib.php` and configuration.
4. Replace the Python loop used by both roles with `mt5/oppw_mt5_continuous_v43.py`. Preserve `oppw-mt5-config.py` and `real-mt5-config.py`.
5. Apply the Android changes to the existing v11/v11.2/v11.3 source:

```powershell
py .\android_patch\apply_v12_patch.py D:\oppw\Mobile
```

The patch creates `.v11.bak` backups of modified Kotlin/Gradle files and sets Android version `12.0.0`, code `20`.

6. Build with JDK 17 and the same Android SDK/signing key used for the existing application:

```powershell
cd D:\oppw\Mobile
.\gradlew.bat clean assembleDebug
```

7. Install over the existing application to preserve its paired encrypted session:

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

## Verification

With a flat account, open **Position** and verify:

- required deposit states that it comes from MT5 `order_calc_margin`;
- 8x shows a -6.25% underlying hard stop;
- 10x shows a -5.00% underlying hard stop;
- the scenario table and decision recorder are visible.

After two non-identical closed trades, open **Analytics** and verify:

- Sharpe is no longer blocked by an arbitrary five-trade minimum;
- Sharpe/Sortino are labeled annualized;
- all four trade-class rows are shown;
- every recent trade has a class;
- the distribution graph runs from best on the left to worst on the right.

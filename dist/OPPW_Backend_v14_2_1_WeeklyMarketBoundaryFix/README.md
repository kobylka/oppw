# OPPW backend v14.2.1 — weekly market boundary fix

Previously, `status.php` accepted only `REGULAR` rows on every weekday. That
correctly excluded Monday premarket, but incorrectly excluded Tuesday through
Friday overnight and premarket candles.

The corrected rule is:

1. Find the first regular-session row of the week.
2. Exclude everything before that timestamp.
3. Include every subsequent Monday–Friday candle, regardless of phase.
4. Exclude Saturday and Sunday rows.

Example:

```text
Monday premarket low             excluded
Monday 15:30+ regular low        included
Monday 21:50 low 28750           included
Tuesday 07:50 low 28700          included
```

After deploying `status.php`, the Overview screen will recalculate from the
existing `strategy_market_points` rows immediately. No Android update, MT5
restart, or SQL migration is required.


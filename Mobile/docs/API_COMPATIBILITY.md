# Backend API compatibility

v10 uses the same authenticated backend endpoint family as v9.1:

```text
auth/pair.php
auth/refresh.php
auth/unpair.php
accounts.php
status.php
analytics.php
events.php
```

Optional push-token paths are attempted in this order:

```text
auth/push-token.php
push-token.php
device-token.php
```

## Closed-trade Sharpe and Sortino

`analytics.php` must return individual trades in one of these arrays:

```text
trades
closedTrades
closed_trades
recentTrades
recent_trades
tradeHistory
```

A trade is treated as closed when at least one of these is true:

- `closed` or `isClosed` is true
- `closedAt`, `closed_at`, `closeTime`, or `exitTime` is populated
- `status` equals `CLOSED`

Return calculation priority:

1. `profit / balanceBefore`
2. `tradeReturn`, `returnFraction`, or equivalent explicit fractional value
3. `returnPercent`, `profitPercent`, or equivalent percentage divided by 100

Open trades are excluded. The Android app does not calculate Sharpe or Sortino from equity history.

## Equity timestamps

Every equity item should contain:

```json
{
  "time": "2026-07-18T10:30:00+02:00",
  "value": 28228.50,
  "deposits": 25000.00
}
```

`date`, `capturedAt`, and `captured_at` are also accepted as timestamp keys. Points without a parseable timestamp are excluded from the chart because a real-time x position cannot be determined safely.

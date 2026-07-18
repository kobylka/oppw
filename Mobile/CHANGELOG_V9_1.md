# OPPW Monitor v9.1 changelog

## Android

- Overview health is derived from the age of the latest stored US100 market tick and is always `OK`, `UNKNOWN`, or `WARNING`.
- Overview shows `Heartbeat: …` for the latest continuous-loop snapshot and `Last tick: …` for the latest US100 market update.
- Flat Saturday/Sunday state is normalized locally even when the app is showing a cached Friday response.
- Weekend next action is `None`; no OH countdown or scheduled-check time is displayed.
- Background stale-loop checks and notifications are skipped on Saturday and Sunday.
- Logs and Overview use the same price-health calculation.
- The all-time deposits series is always populated from backend cash flows or the earliest recorded balance and is drawn as a dashed step line so it remains visible when it overlaps equity.

## Backend

- Flat weekend responses clear next action, next-action time, conditions, and closest condition.
- Price health is calculated from the latest valid `strategy_market_points` row rather than from the old snapshot health string.
- The latest tick timestamp is returned explicitly as `connection.lastTick`.
- Initial deposits fall back to `INITIAL.balance_after` when its amount is zero, then to the earliest positive recorded account balance when no usable INITIAL cash flow exists.
- Account-list health uses the same latest-price logic as the status response.

No database migration or MT5 change is required.

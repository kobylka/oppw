# OPPW Monitor 13.4.0

## Execution timing correction

- Preserves microseconds from `strategy_events.details.event_at` in Analytics API responses.
- Calculates timestamp deltas without truncating events to whole seconds.
- Uses the MT5-measured `order_send()` latency for broker acknowledgement and immediate fills when available.
- Keeps the first successful lifecycle milestone instead of replacing it with a later reconciliation event.
- Displays lifecycle timestamps to milliseconds.
- Displays sub-100 ms measurements with decimal precision instead of rounding them to `0ms`.
- Preserves milliseconds in all backend ISO timestamps and in mobile-receipt latency calculations.

Existing execution records are recalculated from their stored JSON details; no database migration is required.

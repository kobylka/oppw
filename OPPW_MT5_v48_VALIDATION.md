# OPPW MT5 v48 validation

## Automated/static checks

- Python syntax compilation for the v48 loop and all public account templates.
- No references to the v47 file-lock, heartbeat-file, publisher-lock, or shared
  JSONL-spool classes/settings in the v48 loop or templates.
- Exactly three MT5 `order_send()` surfaces remain: BUY, SL/TP modification,
  and market SELL.
- Each `order_send()` is immediately preceded by acquisition and validation of
  the global trade-execution gate.
- BUY claims the account/week record before the MT5 request.
- A `None`/uncertain BUY result persists `UNKNOWN`; a definite rejection
  persists `REJECTED`.
- Snapshot and event ingestion require a valid unexpired role fencing token.
- Executor snapshots are rejected while a dedicated publisher lease is active.
- SQL migration contains role leases, a fenced trade gate, weekly-entry unique
  keys, and historical trade backfill.
- `LIVE_ENABLED`/`LIVE_DISABLED` output follows every AutoTrading banner call.
- The PowerShell installer completed successfully against an isolated temporary
  project tree on Windows PowerShell 5.1.
- The publisher ownership check and its state-transition log execute outside
  the event-queue condition lock, preventing logger/queue lock inversion.
- v48.2 accepts `--conservative-multiplier`, rejects the removed
  `--legacy-balance-multiplier` spelling, and maps the new flag to the unchanged
  2.0× L10 / 2.5× L8 sizing policy.

## Environment limitations

This workspace has no connected MT5 terminal, production MySQL database, or
production HTTPS backend. It also does not provide a PHP executable for local
`php -l` validation. PHP files were statically inspected, but must be linted on
the deployment host:

```powershell
php -l Mobile\backend\lib.php
php -l Mobile\backend\ingest.php
php -l Mobile\backend\coordination.php
php -l Mobile\backend\events-ingest.php
```

Before live use, test these cases on Demo:

1. Start two EXECUTOR processes on different computers; the second must fail.
2. Kill the first process; the second may acquire only after lease expiry.
3. Start PUBLISHER then EXECUTOR; only PUBLISHER sends snapshots, while
   EXECUTOR events still reach MySQL.
4. Disable the backend; no new order may be sent after lease safety expires.
5. Simulate a rejected BUY; the weekly row becomes `REJECTED` and may retry.
6. Simulate an unknown BUY response; the weekly row becomes `UNKNOWN` and a
   second BUY remains blocked.
7. Confirm BUY, SL/TP, and final-session SELL each create a short-lived
   `TRADE_EXECUTION` lease with an increasing fencing token.

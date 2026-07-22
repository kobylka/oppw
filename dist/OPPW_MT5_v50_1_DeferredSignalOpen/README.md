# OPPW MT5 v50.1 — deferred cash-open signal

Build:

```text
2026-07-21-deferred-cash-open-signal-v50.1
```

## Correct early-entry behavior

An intentionally early BUY, such as 09:46 Warsaw time, executes at the live
US100 ask. The strategy's separate cash-open signal reference does not exist
until the official exchange cash open (normally 15:30 Warsaw time).

v50.1 treats those as two distinct events:

1. The early BUY may execute normally.
2. `entry_signal_open_pending` remains true until the exact cash-open M1 bar is
   available.
3. The early fill price is never substituted for the missing signal open.
4. At and after cash open, the loop retries retrieval every cycle until the
   exact signal open is captured and persisted.
5. Restarting before or after cash open preserves this lifecycle.
6. CH and break-even calculations cannot run with a fabricated reference.
7. Final-week TO remains unconditional even if signal data is unavailable.

Snapshots now expose:

```text
position.entrySignalOpen
position.entrySignalOpenPending
position.entrySignalCaptureAt
position.entrySignalReferenceSource
```

Before cash open, the break-even payload reports
`WAITING_FOR_SIGNAL_OPEN`. If the bar is late after cash open, it reports
`CAPTURE_RETRY` and the loop continues trying.

## Install

Stop PUBLISHER and EXECUTOR, then run from this package directory:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_v50_1.ps1 `
  -RepoRoot D:\oppw
```

Restart PUBLISHER first, followed by EXECUTOR. No SQL, PHP, Android, or config
change is required.

Expected early-entry log:

```text
EVENT ENTRY_SIGNAL_OPEN_PENDING ... capture_at=2026-07-20T15:30:00+02:00 entry_fill_reference=not_used
```

Expected cash-open log:

```text
EVENT ENTRY_SIGNAL_OPEN_CAPTURED day=2026-07-20 symbol=US100 price=...
```

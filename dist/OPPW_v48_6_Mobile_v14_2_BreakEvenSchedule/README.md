# OPPW MT5 v48.6 / Mobile v14.2

The first open-position ticket card now displays the next break-even arming
check, its live countdown, and the signal-close threshold.

## Scheduling rules

- The entry day itself is not eligible.
- The first check is after the completed signal-session close on the next
  exchange trading day.
- The timestamp comes from the XNYS calendar's session close plus the existing
  one-minute close-processing delay, so DST mismatch weeks and holidays are
  handled automatically.
- Once a day's close has been processed, the display advances to the following
  eligible trading day.
- The final trading day is excluded because weekly TO is scheduled before that
  close-processing check.
- If break-even is already armed, the card displays `Already armed` and notes
  that continuous price checks are active.

The first ticket card includes:

```text
Next break-even check: 21 Jul 22:01:00
Countdown: 05:14:32
Arms if completed signal close is below ...
```

## Install

1. Stop PUBLISHER and EXECUTOR.
2. Run `install_v48_6.ps1 -RepoRoot D:\oppw`.
3. Restart PUBLISHER first, then EXECUTOR.
4. Install `android/OPPW-Monitor-v14.2-debug.apk` over the existing app.

Expected MT5 build:

```text
2026-07-21-break-even-schedule-v48.6
```

No backend or SQL migration is required.


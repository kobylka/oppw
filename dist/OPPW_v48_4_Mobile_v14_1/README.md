# OPPW v48.4 / Mobile v14.1

This maintenance release fixes two monitoring issues without changing trade
entry, exit, sizing, or protection logic.

## Fixes

- Current-week open, high, low, and close accept the publisher's actual phase
  labels such as `Monday Regular`. Premarket rows remain excluded.
- An open position's displayed deposit comes directly from
  `mt5.account_info().margin` instead of being recalculated at the changing
  current price.
- Exposure and effective leverage use that broker-reported margin and account
  balance, so unrealized P/L does not make effective leverage drift through
  changing equity.

What-if sizing continues to use `order_calc_margin`; this release changes only
the reporting of margin already used by an open position.

## Deployment

1. Stop the REAL and DEMO publisher/executor processes.
2. Copy `mt5/oppw_mt5_continuous_v48_4.py` to each account's active
   `oppw_mt5_continuous.py` runtime path.
3. Upload `backend/status.php` to the production backend.
4. Restart PUBLISHER first, then EXECUTOR.
5. Install `android/OPPW-Monitor-v14.1-debug.apk` over the existing app.

The MT5 startup log must contain:

```text
build=2026-07-20-market-stats-direct-margin-v48.4
```

No SQL migration or configuration change is required.

## Important margin scope

MT5 exposes account-level used margin through `account_info().margin`, not a
separate margin field on each Python position. OPPW's one-position policy makes
that value the authoritative deposit for its live trade. If unrelated positions
are opened in the same MT5 account, the displayed deposit will include their
margin as well.

# OPPW MT5 v49.2

Build:

```text
2026-07-21-deferred-tsl-install-v49.2
```

V49.2 retains the v49 immutable filled-position hard stop and the market exits
for BEPRE, BEO, BH and a crossed TSL.

## TSL decision flow

The continuously running protection loop now follows:

```text
bid <= normalized TSL
    -> fenced market SELL, reason TSL

bid > TSL and TSL is broker-valid
    -> install TSL through TRADE_ACTION_SLTP

bid > TSL but TSL is inside stop/freeze distance
    -> keep the existing hard SL unchanged
    -> send no bracket and no SL/TP modification
    -> retry on the next loop cycle (normally 0.20 seconds)
```

If price rises enough, the next cycle installs the TSL. If price reaches the
TSL first, the next cycle sends the TSL market close.

An already installed correct or tighter SL is accepted before checking broker
stop/freeze distance. `modify_sltp()` also no longer clamps an identical active
SL downward merely because that existing level is now inside the freeze zone.

State changes are logged only on transition:

```text
EVENT TSL_INSTALL_DEFERRED ... retry=next_cycle
EVENT TSL_INSTALL_RETRY_READY ...
```

## Installation

Stop PUBLISHER and EXECUTOR, then run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_v49_2.ps1 `
  -RepoRoot D:\oppw
```

Restart PUBLISHER first, then EXECUTOR. No config, backend, SQL, Android or
state migration is required. Private configurations, state and logs are not
overwritten.

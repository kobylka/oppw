# OPPW MT5 v49.1

Build:

```text
2026-07-21-tsl-cross-market-exit-v49.1
```

V49.1 retains the complete v49 immutable filled-position hard-stop invariant
and market BEPRE/BEO/BH exits.

## Crossed TSL rule

Whenever the TSL regime is active, the executable threshold is normalized in
the same way as broker SL prices:

```text
TSL threshold = round upward to whole point(entry price × 0.996)
```

Before attempting an SL/TP modification, the executor compares the fresh live
bid with this threshold:

```text
if bid <= TSL threshold:
    send fenced market SELL with reason TSL
```

This covers a Thursday activation below the threshold, a premarket gap, a
Friday gap, recovery after an outage, a missing broker SL, or any other move
through the active TSL.

The crossed TSL does not call `arm_exit()` and does not attempt a near-market
exit bracket first. If the market SELL fails and the position remains visible,
the existing latched-exit fallback can still protect a later cycle.

When bid remains above the TSL but the broker's stop/freeze distance prevents
installation, the existing protective fallback remains unchanged because the
actual TSL price has not yet been crossed.

Expected log:

```text
EVENT TSL_MARKET_EXIT_REQUIRED ...
EVENT SELL_REQUEST reason=TSL ...
EVENT SELL_ACCEPTED reason=TSL ...
```

## Install

Stop PUBLISHER and EXECUTOR, then run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_v49_1.ps1 `
  -RepoRoot D:\oppw
```

Restart PUBLISHER first, then EXECUTOR. Private configurations, strategy state
and logs are not overwritten. No backend, SQL, Android or config change is
required.

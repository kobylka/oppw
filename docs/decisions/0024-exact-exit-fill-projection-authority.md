# ADR 0024: Exact exit fills outrank close-projection fallbacks

- Status: Accepted
- Date: 2026-07-30
- Extends: ADR 0002 and ADR 0003

## Context

The executor and publisher are separate processes. A publisher can observe and publish a flat position before the executor's `POSITION_CLOSED` and `EXIT_FILLED` events reach the backend. The first flat snapshot must close the mutable `strategy_trades` projection promptly, but its only immediately available fallback may be an older installed hard SL. Treating that fallback as final can report the wrong close price, return, reason, and trade class after a crossed-threshold market exit.

The executor also retained both its market-exit latch and the broker protection that preceded it. Close finalization allowed that older protection price to override the confirmed market fill.

## Decision

An exact MT5 SELL fill with a deal ticket is the final price authority for a market exit. The executor persists the request bid with the exit latch, replaces it with the confirmed deal price when available, and never lets an older installed SL or TP override a latched market exit. A Thursday premarket gap through the newly-active unified TSL uses the established `TSL1PRE` exit reason.

The backend may provisionally close `strategy_trades` from a flat snapshot and protection fallback. In every delivery order it prefers a previously stored exact `EXIT_FILLED` record, and a later exact fill idempotently repairs the closed projection's time, price, reference, slippage, return, reason, excursions, and derived class. Immutable execution, fill, protection, and trade-transition rows are not rewritten.

## Consequences

- Publisher/executor delivery order cannot make an old hard SL the final record for a market exit.
- Broker-side protective closes without an exact deal retain the installed-protection fallback.
- Replaying an identical immutable fill is allowed to converge the mutable projection without changing authority rows.
- Existing incorrect projections require a guarded operational update from their immutable exact fills; no schema migration is required.

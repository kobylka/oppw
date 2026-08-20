# ADR 0039: Deferred TMS TSL1PRE market exit

- Status: Accepted
- Date: 2026-08-20
- Extends: ADRs 0002, 0032, 0034, and 0038

## Context

The unified Thursday TSL becomes active at 00:00 Europe/Warsaw. Bossa accepts a market SELL then, but TMS begins accepting orders at 00:01. A TMS TSL1PRE request sent at 00:00 is rejected with MT5 retcode 10018. The existing executor latched the exit reason before `order_send`; after rejection, standard protection interpreted that latch as an instruction to install an exit SL/TP bracket. This both obscured the expected session rejection and stopped retrying the intended market exit.

A local-only delay would avoid the first request but would lose an already observed threshold crossing on Master-to-Backup failover or after price recovered above the threshold.

## Decision

Add the strategy-relevant per-account setting `tsl1pre_market_exit_delay_seconds`, with a canonical zero default. Both TMS private configurations set it to 60 seconds; Bossa remains zero and behaviorally unchanged. The boundary is measured from the Thursday date change in the configured strategy timezone, not from the cycle that observes the crossing.

Before deferring a TMS TSL1PRE SELL, the current EXECUTOR records a deterministic, position-scoped `TSL1PRE` trigger in immutable `strategy_position_rule_trigger_events` under its valid global lease and fencing token. It records the exact bid, normalized TSL threshold, trigger time, and not-before time. TSL1PRE is a system rule with control revision zero; it is never shown as or governed by a Mobile toggle. The existing table and canonical `strategy-controls.php` capability are extended because they already own recoverable position-scoped exit authorization.

While waiting, the immutable hard SL remains broker-side. At or after the not-before time, the executor submits the normal fresh-bid, priority-delayed and globally fenced market SELL. Any failed check, coordination attempt, or broker rejection retains the pending market intent and retries it under the normal request throttle; it must not fall through to exit-bracket installation. Startup and failover reload the immutable trigger before protection processing, so price recovery cannot cancel an authorized exit.

## Consequences

- TMS no longer submits the known-invalid Thursday 00:00 market order.
- A retcode 10018 after the boundary remains an explicit rejected lifecycle attempt followed by a retry, rather than changing the exit type.
- Bossa and non-TSL1PRE exits retain their established timing and protection behavior.
- TMS configuration must contain the same 60-second override on Master and Backup.
- The resolved delay changes the immutable strategy specification hash.

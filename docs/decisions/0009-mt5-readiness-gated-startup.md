# ADR 0009: Readiness-gated global MT5 startup

- Status: Accepted; fixed two-account ordering portion superseded by ADR 0032
- Date: 2026-07-23
- Supersedes: the time-based per-account startup sequencing in ADR 0008

## Context

Manual Demo and Real executor launches succeeded when performed sequentially, while service launches failed with MT5 IPC timeouts. The supervisor started both account executors in the same reconciliation pass and considered a live Python PID sufficient evidence of readiness. A process could remain alive for the full MT5 initialization timeout while another terminal initialization began concurrently. Time-based publisher delay did not serialize Demo against Real and did not prove that any terminal was connected.

## Decision

Start assigned MT5 children globally in this fixed order: Demo Executor, Real Executor, Demo Publisher, Real Publisher. Every service-launched canonical loop receives a unique private readiness-file path. The loop atomically publishes readiness only after `mt5.initialize`, expected-account verification, required symbol selection, and executor AutoTrading validation succeed.

The supervisor launches at most one unready child. It does not advance while a child is initializing. Missing readiness after a bounded timeout stops that child, and an early exit or timeout applies bounded per-role restart backoff. During that backoff another assigned role may initialize, preserving independent account availability without overlapping MT5 initialization. Stale readiness is removed before every launch and after supervised stop.

## Consequences

- MT5 IPC initialization cannot overlap across Demo, Real, Executor, or Publisher children.
- A PID alone is never reported internally as successful startup.
- Failure of one role cannot indefinitely block the other account; later eligible roles may start only after the failed attempt has exited or timed out.
- Backend assignment, role leases, fencing, process-stop controls, and trading logic remain unchanged.

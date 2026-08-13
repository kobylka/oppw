# ADR 0034: Real-first account startup and market-order priority

- Status: Accepted
- Date: 2026-08-13
- Supersedes: the configured account ordering portion of ADR 0032

## Context

Four broker accounts can initialize or reach the same scheduled market action together. Configuration-list order and independent process scheduling did not guarantee that capital-bearing Real accounts acted before Demo accounts.

## Decision

Use the canonical priority `REAL`, `REAL_TMS`, `DEMO`, `DEMO_TMS`. Apply it to serialized supervisor startup for both roles. Stagger live BUY and market SELL submission with audited per-account delays of `0.0`, `0.1`, `1.0`, and `1.5` seconds. Include the resolved delay in the immutable strategy specification. Do not delay SL/TP protection operations. If a higher-priority account is stopped, failed, or otherwise ineligible, it does not block later accounts.

## Consequences

- REAL BOSSA starts first and submits simultaneous market orders first under normal concurrent eligibility.
- REAL TMS precedes both Demo accounts.
- Safety-critical broker protection remains immediate.
- Process failure cannot make a lower-priority healthy account miss its independent trading opportunity.

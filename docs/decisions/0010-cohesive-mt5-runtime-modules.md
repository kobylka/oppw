# ADR 0010: Cohesive MT5 runtime modules

- Status: Accepted
- Date: 2026-07-27

## Context

The sole MT5 entrypoint had grown beyond 5,600 lines. Configuration, persistence, global coordination, publishing, exchange sessions, position recovery, strategy decisions, monitoring, broker execution, and runtime orchestration shared one file. Although there was only one canonical copy, unrelated changes still produced large diffs and required excessive context, increasing regression risk.

## Decision

Keep `mt5/oppw_mt5_continuous.py` as the only executable entrypoint and public compatibility surface. Extract its implementation into the fixed `mt5/oppw_core/` package by cohesive responsibility:

- account configuration;
- state/value models;
- logging and pure utilities;
- MySQL coordination and fencing;
- mobile publication;
- session/calendar and market data;
- position lifecycle and recovery;
- strategy decisions and sizing previews;
- monitoring and snapshots;
- broker execution and protection;
- runtime orchestration.

`OPPWContinuousStrategy` remains the canonical strategy type. It composes behavior-preserving mixins while retaining connection/bootstrap methods in the entrypoint. The extraction does not change strategy rules, method signatures, broker requests, persistence, event payloads, scheduling, or state fields. Existing callers and tests continue importing the canonical entrypoint rather than internal modules.

Repository validation enforces the exact module set and a thin composition root. The release gate compiles and packages every `oppw_core` module.

## Consequences

Future work can load and change one bounded subsystem without recreating the entire execution context. Diffs become smaller and ownership is explicit. Cross-module behavior still operates on one strategy instance, so existing ordering and state invariants remain intact. Moving a method between modules is architectural work and requires boundary tests; creating an alternate entrypoint or parallel implementation remains prohibited.

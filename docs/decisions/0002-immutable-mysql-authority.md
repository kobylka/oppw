# ADR 0002: Immutable MySQL authority with diagnostic events

- Status: Accepted
- Date: 2026-07-22

## Context

General events were previously asked to serve as status, audit history, lifecycle evidence, and recovery state. That made classification and execution history dependent on logs and mutable projections.

## Decision

Use dedicated immutable/idempotent MySQL tables for specifications, decisions, execution stages, fills, protection changes, trade transitions, and cash flows. Keep `strategy_events` as a diagnostic stream. Keep snapshots and `strategy_trades` as mobile projections rather than immutable authority.

## Consequences

Business history is queryable and stable even when logs are sampled or projections change. Ingestion is more structured and every new authoritative record type requires schema, persistence, and contract tests.

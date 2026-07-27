# ADR 0012: Bounded current-snapshot projection

- Status: Accepted
- Date: 2026-07-27

## Context

The publisher sent a complete mobile snapshot every five seconds and ingestion appended every payload to `strategy_snapshots`. Runtime consumers selected only the newest row, while authoritative history already lived in dedicated decisions, stages, fills, protection, trade, cash-flow, equity, market, and event tables. The unused snapshot history grew to approximately 6 GB.

## Decision

Treat `strategy_snapshots` strictly as a mutable current-state projection. Enforce one row per `strategy_key` with a unique index. Ingestion starts a transaction, locks and reads the existing account row for transition detection, and then upserts the new payload into that same row. Status and account-list endpoints join directly by the unique account key.

Historical snapshots are not archived or retained. The existing legacy table is an operator-approved disposable projection and may be dropped before applying the forward migration, which recreates the bounded table. Authoritative historical records and the separate equity and market series are unaffected.

## Consequences

- Snapshot storage is bounded by the number of configured accounts rather than publication frequency.
- Open/close, funding, connection, and protection-loss transitions still compare the current payload with the immediately preceding accepted payload.
- The global publisher lease remains the primary writer coordinator; the row lock and unique key provide database-level serialization and boundedness.
- Dropping the projection temporarily makes mobile status unavailable until the next accepted publisher snapshot.

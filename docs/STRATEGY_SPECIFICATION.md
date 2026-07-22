# OPPW24 strategy specification authority

The running loop stores one canonical, hash-addressed strategy specification in MySQL for every resolved configuration. The runtime document—not this prose summary—is the authoritative record of the strategy that produced a decision.

## Identity and versioning

The specification version is read from the repository root `VERSION` file. The loop recursively sorts the canonical JSON document, serializes it without insignificant whitespace, and calculates SHA-256. The database stores:

- `spec_id`: the first 32 hexadecimal characters of the SHA-256 hash;
- `spec_hash` and `document_hash`: the complete SHA-256 hash;
- `spec_key`: `OPPW24`;
- project version, effective time, build ID, instruments, and the complete JSON document.

Changing a trading-relevant resolved value creates a different hash and a new immutable specification row. Credentials, account numbers, local paths, and tokens are excluded.

## Authoritative contents

The document records instruments and sources, exchange session clocks, entry rules, leverage selection, sizing, session-indexed targets, PRE H ramps, OH/CH/break-even/TSL/hard-stop rules, order semantics, the immutable hard-stop invariant, exit hierarchy, and authoritative MySQL tables.

## Immutable authority tables

| Record | Authoritative table |
|---|---|
| Strategy specification | `strategy_specifications` |
| Account/spec adoption | `strategy_account_spec_assignments` |
| Strategy decision | `strategy_decisions` |
| Execution lifecycle stage | `strategy_execution_stages` |
| Fill | `strategy_fills` |
| Protection request/result | `strategy_protection_changes` |
| Trade transition ledger | `strategy_trade_ledger` |
| Cash flow | `account_cash_flows` |

`strategy_trades` is a mutable projection for mobile analytics. `strategy_events` is a diagnostic stream and legacy compatibility source; neither replaces the immutable audit records.

## Immutability and idempotency

Authority tables use deterministic identifiers and idempotent insertion. Database triggers reject updates and deletions. Retransmitting an identifier with a different specification or payload hash fails instead of rewriting history.

The complete specification remains available in status snapshots. Its explicit persistence command is sent until the backend acknowledges the exact ID and full hash; routine snapshots do not rewrite it afterward.

## Exact and reconciled fills

Market fills containing an MT5 deal ticket are stored as exact fills. If a broker-side SL closes a position and the loop observes only that the position disappeared, the loop records a reconciliation fill with `is_exact = 0` and source `POSITION_DISAPPEARANCE_RECONCILIATION`. It is never presented as an exact broker deal.

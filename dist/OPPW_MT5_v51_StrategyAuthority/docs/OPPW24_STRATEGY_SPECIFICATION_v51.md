# OPPW24 strategy specification authority — v51

v51 stores one canonical, hash-addressed strategy specification in MySQL for every resolved configuration used by a running loop. The runtime document—not a prose summary—is the authoritative record of the strategy that produced a decision.

## Identity and versioning

The loop builds a canonical JSON document, recursively sorts object keys, serializes it without insignificant whitespace, and calculates SHA-256. The database stores:

- `spec_id`: the first 32 hexadecimal characters of the SHA-256 hash;
- `spec_hash` and `document_hash`: the complete 64-character SHA-256 hash;
- `spec_key`: `OPPW24`;
- `spec_version`: `51.0`;
- effective time, build ID, execution symbol, signal symbol, and the complete JSON document.

Changing any trading-relevant resolved value creates a different hash and therefore a new immutable specification row. Credentials, account numbers, local paths, and tokens are excluded.

## Authoritative contents

The document records:

- signal and execution instruments and sources;
- exchange calendar, time zones, fallback session times, BUY lead, other-action lead, and entry window;
- first-session-of-week entry rule and deferred cash-open signal reference;
- leverage-selection inputs and thresholds;
- volume sizing, balance-multiplier profile, margin rule, and broker volume-step rule;
- session-indexed TPP values, holiday shifting, and PRE H ramp/formulas;
- OH, CH, break-even, Thursday TSL, and hard-stop formulas;
- market-order and broker-side protection semantics;
- the immutable definitive hard-stop invariant;
- the ordered exit hierarchy;
- the MySQL tables that are authoritative for every historical record class.

## Immutable authority tables

| Record | Authoritative table |
|---|---|
| Strategy specification | `strategy_specifications` |
| Account/spec adoption history | `strategy_account_spec_assignments` |
| Strategy decision | `strategy_decisions` |
| Execution lifecycle stage | `strategy_execution_stages` |
| Fill | `strategy_fills` |
| Protection request/result | `strategy_protection_changes` |
| Trade transition ledger | `strategy_trade_ledger` |
| Cash flow | `account_cash_flows` |

`strategy_trades` remains a mutable materialized projection for mobile analytics. It is not the immutable audit source. `strategy_events` remains a diagnostic stream and legacy compatibility source; it is not the sole historical record.

## Immutability and idempotency

Authority tables use deterministic record identifiers and `INSERT IGNORE` for idempotent retransmission. Database triggers reject `UPDATE` and `DELETE` on immutable tables. If a previously used decision ID is retransmitted with different specification or payload hashes, ingestion fails instead of rewriting history.

The complete specification is included in snapshots for display. A top-level specification persistence command is sent until the backend acknowledges the exact ID and full hash; subsequent routine snapshots do not rewrite it.

## Exact and reconciled fills

Market fills containing an MT5 deal ticket are stored as exact fills. When a broker-side SL closes a position and the loop observes only that the position disappeared, v51 stores a clearly labelled reconciliation fill with `is_exact = 0` and source `POSITION_DISAPPEARANCE_RECONCILIATION`. It is never represented as an exact broker deal.


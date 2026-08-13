# OPPW24 strategy specification authority

The running loop stores one canonical, hash-addressed strategy specification in MySQL for every resolved account configuration. Named Demo and Real accounts may resolve different private `OVERRIDES`; each account key adopts its own resulting specification. The runtime document—not this prose summary—is the authoritative record of the strategy that produced a decision.

## Identity and versioning

The specification version is read from the repository root `VERSION` file. The loop recursively sorts the canonical JSON document, serializes it without insignificant whitespace, and calculates SHA-256. The database stores:

- `spec_id`: the first 32 hexadecimal characters of the SHA-256 hash;
- `spec_hash` and `document_hash`: the complete SHA-256 hash;
- `spec_key`: `OPPW24`;
- project version, effective time, build ID, instruments, and the complete JSON document.

Changing a trading-relevant resolved value creates a different hash and a new immutable specification row. Credentials, account numbers, local paths, and tokens are excluded.

The resolved sizing document includes the active required-balance multiplier and profile. Bossa uses the canonical `1.765`; the prepared TMS account overrides use `1.5`. With `brokerExposureMultiplier = 20`, the latter permits a theoretical maximum effective exposure of `20 / 1.5 = 13.333x`, subject to broker volume steps and available margin. Each TMS account therefore produces and adopts a specification hash distinct from Bossa.

## Session-order invariants

- Four per-account entry-loss controls are read from MySQL before a controlled entry: `ARITHMETIC_LAST_TWO`, combined `GAP_MOMENTUM`, `TUESDAY_NORMALIZATION`, and combined `PREMARKET_LOW`.
- Arithmetic skips when the latest two weekly outcomes sum to at most −2.00%; an explicit skipped week contributes `0.0`, while an entered week contributes its closed trade's pre-leverage price return.
- The combined gate requires cash-open gap ≥1.00% and prior 20-session momentum ≤−0.50%. On Monday it defers to Tuesday; when Tuesday is the first actual weekly session it skips without a later re-entry.
- A deferred Tuesday entry proceeds only when the Tuesday cash open is within ±0.50% of the prior Friday close, unless that individual rule is disabled.
- The single premarket-low rule requires both a premarket range ≥0.80% and a close in the bottom 15% of that range. Disabling `PREMARKET_LOW` disables the complete conjunctive rule.
- Any enabled market-input rule moves BUY evaluation from the pre-open lead to cash open, still within the existing 55-second entry window. The fenced backend records the entry approval against the exact control revision before BUY; a stale revision, missing backend authority, or missing required market data never permits BUY.

- OH is never evaluated on the first actual XNYS trading session of the week. Its cash-open-minus-lead checks begin on the second actual session, including holiday-shifted weeks and manually adopted positions.
- Break-even can arm only after a false CH at day close, no earlier than the second actual XNYS session and never on the position opening day. Capturing a pending entry-session cash-open signal reference is not a break-even check.
- A manually adopted position receives the same immutable hard-stop lock and broker-side protection restoration as a strategy-opened position before other cycle logic runs.
- A manually adopted position with no valid `L8`/`L10` MT5 comment resolves leverage from the same authoritative prior-week/prior-trade leverage decision as a strategy entry. Any manual-position hard-stop lock created with a conflicting inferred leverage is corrected once using its original balance-at-fill baseline, regardless of a stale execution source label; stale strategy execution/decision linkage is removed during adoption.
- The current-week monitoring summary aggregates live MT5 M1 candles from the first actual XNYS cash open. While a current-week manual position is adopted, its opening timestamp becomes the observation boundary and its fill price is included in weekly open/high/low, including positions opened before or exactly at cash open. The exact cash-open M1 price remains a separate strategy reference.
- The unified 0.4% TSL becomes active at the Thursday date change. If the Thursday premarket bid is already through that threshold, the globally fenced market exit is labeled `TSL1PRE`; other crossed-threshold TSL market exits retain `TSL`.
- A market exit initially retains its request bid, then replaces it with the confirmed MT5 deal price. That exact fill outranks any older broker SL/TP when producing the close record.
- When a broker SL or TP removes the position, the executor reads the completed MT5 SELL deal for that position before clearing local state. The deal reason selects the matching SL/TP label, and its exact price and timestamp are published as `EXIT_FILLED`. Missing deal history defers reconciliation and prevents another entry.

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
| Entry-rule control changes | `strategy_entry_rule_control_events` |
| Weekly entry-rule transitions | `strategy_entry_rule_week_events` |

`strategy_entry_rule_controls` and `strategy_entry_rule_week_state` are mutable current projections backed by their immutable event tables. `strategy_trades` is a mutable projection for mobile analytics and supplies closed pre-leverage outcomes to entry control. `strategy_events` is a diagnostic stream and legacy compatibility source; neither replaces the immutable audit records.

## Immutability and idempotency

Authority tables use deterministic identifiers and idempotent insertion. Database triggers reject updates and deletions. Retransmitting an identifier with a different specification or payload hash fails instead of rewriting history.

The complete specification remains available in status snapshots. Its explicit persistence command is sent until the backend acknowledges the exact ID and full hash; routine snapshots do not rewrite it afterward.

## Exact and reconciled fills

Market fills containing an MT5 deal ticket are stored as exact fills. A publisher flat snapshot may temporarily record a reconciliation fill with `is_exact = 0` and source `POSITION_DISAPPEARANCE_RECONCILIATION`; it is never presented as an exact broker deal. The executor does not finalize a disappeared position until completed MT5 deal history supplies the exact SELL deal. Its `EXIT_FILLED` record repairs and outranks any provisional disappearance-based trade projection.

The strategy decision bound immediately before `SIGNAL` remains the execution and trade-entry decision for that lifecycle. Later next-entry or flat-account what-if calculations never replace it. Entry stages emitted before MT5 supplies a position ticket remain linked through their execution ID and the later `POSITION_VISIBLE` ticket. A broker-triggered SL/TP close does not fabricate `EXIT_CHECKED`, `EXIT_SENT`, or `EXIT_ACCEPTED`; those stages apply only to an executor-submitted market SELL.

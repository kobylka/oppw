# ADR 0028: Mobile-controlled, globally fenced entry-loss rules

- Status: Superseded in part by ADR 0029
- Date: 2026-08-11

## Context

The production loop needed the researched weekly loss controls: a two-outcome arithmetic loss gate, a combined opening-gap and 20-session-momentum gate, a Tuesday normalization re-entry, and a premarket range/close-location gate. Demo and Real also need independent runtime enablement for each of the five operator-visible conditions. Local files cannot own these settings because master/backup failover could otherwise produce different decisions.

## Decision

`strategy-controls.php` is the single API owner for per-account entry-rule controls and weekly defer/skip state. The five stable rule keys are `ARITHMETIC_LAST_TWO`, `GAP_MOMENTUM`, `TUESDAY_NORMALIZATION`, `PREMARKET_RANGE`, and `PREMARKET_CLOSE_NEAR_LOW`. Gap and momentum are one switch and one conjunctive rule. The two premarket switches are independently visible prerequisites of the one premarket-low gate; disabling either disables that composite gate.

Controls are a mutable per-account projection with immutable control-event audit. Mobile changes require the account's existing operational-control grant. Weekly entry approvals and defer/skip transitions require the active global EXECUTOR lease and are stored in a projection with immutable event audit. The backend rejects an approval or transition if its control revision became stale. A Monday defer may transition only to Tuesday re-entry or Tuesday normalization skip; other final decisions cannot be rewritten.

The arithmetic rule uses the two latest weekly outcomes. Closed strategy trades contribute their pre-leverage price return and an explicitly skipped week contributes zero. The arithmetic threshold is −2.00%. The combined rule requires a cash-open gap of at least 1.00% and prior 20-session momentum of at most −0.50%. A Monday match defers; a holiday Tuesday match skips. Deferred Tuesday entry requires an open within ±0.50% of the prior Friday close unless that rule is disabled. The premarket gate requires both a range of at least 0.80% and a close in the bottom 15% of that range.

Enabled market-input rules move the entry evaluation to cash open, inside the existing bounded entry window. Missing rule settings, fencing authority, or required market input never permits a BUY. The canonical strategy specification records the fixed semantics and thresholds; each decision records the active per-account control revision and values.

## Consequences

- Demo and Real can use different rule settings without private configuration drift.
- Master/backup takeover observes one weekly defer/skip state and cannot legitimately reverse a final skip.
- The operational-control grant can resume the executor and can change its entry rules, so it remains a privileged pairing capability.
- Control and weekly-rule audit tables remain online indefinitely and are included in backup/restore validation.

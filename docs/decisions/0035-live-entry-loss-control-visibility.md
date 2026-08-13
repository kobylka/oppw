# ADR 0035: Live entry-loss-control visibility

- Status: Accepted
- Date: 2026-08-13

## Context

The mobile settings screen showed whether each weekly entry-loss rule was enabled, while the Position screen showed neither disabled rules nor the inputs and thresholds currently approaching a weekly entry decision. Operators could not distinguish a disabled rule, an unavailable input, a non-match, and a live match.

## Decision

Keep `strategy-controls.php` as the setting and recent-outcome authority. Permit a valid fenced PUBLISHER lease to read that context; only EXECUTOR may record weekly state. Add a `lossControls` object to the flat-account what-if snapshot. It always contains the four canonical rules in order with enablement, applicability, status, effect, and all structured comparisons. Price-dependent mobile comparisons use the current MT5 BUY price. At the pre-open BUY action, the EXECUTOR uses a fresh MT5 BUY price as the authoritative entry reference, evaluates all loss-control rules, records the fenced decision, and dispatches an allowed BUY in the same cycle without waiting for the regular-session M1 bar. Android joins the snapshot with its separately authenticated current control projection and shows every rule and threshold on the Position screen.

## Consequences

- Disabled rules remain visible with live informational comparisons.
- Missing inputs display as waiting rather than silently passing.
- Mobile presentation cannot authorize an entry or replace the executor's fenced decision.
- The added snapshot field is optional for compatibility with older stored snapshots and publishers.

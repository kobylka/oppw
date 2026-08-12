# ADR 0029: One premarket-low entry control

- Status: Accepted
- Date: 2026-08-12
- Supersedes: ADR 0028's two independently visible premarket switches

## Context

The premarket range threshold and close-location threshold are two required inputs to one loss-protection condition. Exposing them as separate Mobile controls incorrectly suggested that either threshold was an independently meaningful rule.

## Decision

The per-account entry-control contract exposes four keys. `PREMARKET_LOW` replaces `PREMARKET_RANGE` and `PREMARKET_CLOSE_NEAR_LOW`. When enabled, it skips entry only when the premarket range is at least 0.80% and the premarket close is in the bottom 15% of that same range. Disabling it disables the complete conjunctive condition.

The forward migration replaces the two stored booleans with `premarket_low_enabled`. For an existing account, the new value is the logical AND of the two legacy values so an operator-disabled prerequisite never becomes enabled during migration. Existing immutable audit events retain their historical rule keys.

This breaking control-key transition begins with product release 56.0.0. The compatible Android UI/contract update begins with Android release 17.1.0.

## Consequences

- Mobile shows one premarket control with both thresholds in its label and description.
- The continuous loop consumes exactly one premarket control key.
- Historical audit rows remain truthful records of the contract active when they were written.
- The migration must be applied before deploying the updated PHP endpoint and MT5 runtime.

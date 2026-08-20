# ADR 0038: Mobile-controlled OR5 position-loss protection

- Status: Accepted
- Date: 2026-08-20
- Extends: ADR 0002, ADR 0003, ADR 0028, ADR 0031, and ADR 0035

## Context

The researched OR5 loss rule exits an already-open position from completed M1 market structure. Treating it as an entry-rule revision would couple unrelated weekly-entry authority to a position lifecycle. A local-only switch would also let master and backup disagree, while acting directly from a Mobile toggle or mutable snapshot would cross the execution-authority boundary.

## Decision

Keep `strategy-controls.php` as the single strategy-control endpoint and reuse the paired device's operational-control permission, but give open-position rules an independent `strategy_position_rule_controls` projection and revision. The sole rule key is `OR5`; its deployment default is disabled. Setting changes are retained in immutable `strategy_position_rule_control_events`.

OR5 evaluates only a newly completed M1 candle from the affected account's MT5 terminal, never the forming candle or MySQL monitoring history. Its fixed conjunction is: signal-bar low at least 0.50% below actual entry, signal close at or below the low of the first five regular-session M1 bars, and a trailing 60-M1 first-open-to-minimum-low decline of at least 1.50%. Persistence is one completed close. Entry-day slow history begins no earlier than the later of cash open or position open; carried days may use the configured same-day premarket start. Every required minute must be exact.

Startup, an observed enablement, or any observed position-control revision creates a forward-only evaluation boundary. No previously completed candle is applied retrospectively. Missing broker bars, backend authority, or current fencing fails closed for new OR5 exits while broker-side hard-stop protection remains.

Before SELL, the active EXECUTOR records a deterministic, revision-matched trigger in immutable `strategy_position_rule_trigger_events` under its global lease and fencing token. The trigger contains the position identity, completed signal time, thresholds, exact market inputs, and payload hash. Once authorized, the position-scoped OR5 exit is latched and retried across failures or failover; disabling the mutable rule cannot cancel it. Execution continues through `EXIT_SIGNAL`, `EXIT_CHECKED`, `EXIT_SENT`, `EXIT_ACCEPTED`, and exact `EXIT_FILLED` authority.

Android shows OR5 in a separate open-position settings section and renders its live completed-candle comparisons on the open Position screen. It remains an operator-control and monitoring client, not an execution principal.

## Consequences

- Entry-rule revisions and weekly state remain unchanged by OR5 toggles.
- Master and backup share one control revision and one recoverable trigger authorization.
- A toggle affects only future completed candles; it cannot retroactively exit or cancel an authorized exit.
- The new control, audit, and trigger tables are included in ordered migration, backup/restore, contract, MT5, PHP, and Android validation.

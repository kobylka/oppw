# v13 proposals — not implemented

## 1. Institutional pre-trade risk panel

Turn the current ticket into a multi-state risk worksheet: current account, proposed account, and stressed account. Add configurable shocks, spread widening, overnight-gap assumptions, commission/slippage reserves, broker stop-distance validation, and explicit pass/warn/block pre-trade checks. Preserve each preview as an immutable decision record.

## 2. Searchable strategy decision history and replay

Persist every distinct decision as a first-class database row rather than only an event string. Store all inputs, source timestamps, source identities, selected leverage, sizing, risk outputs, code build, and final action. Add filters by account/week/outcome and a replay view comparing the recorded result with a recalculation under the current build.

## 3. Deeper analytics

Add filters by account, leverage, year, exit reason, trade class and market regime. Show confidence intervals and sample sizes beside ratios, rolling trade Sharpe/Sortino, class transition matrices, cumulative contribution by class, and benchmark comparisons. Keep raw trade returns exportable so every chart can be independently verified.

## 4. Operations and reconciliation

Create one screen comparing MT5 terminal, executor state, publisher state, backend snapshot and mobile cache. Each field should show value, timestamp, age and authority. Mismatches become persistent incidents with actions such as republish, reload state, and export diagnostics. MT5 remains authoritative for positions, deals, live prices and broker margin.

## 5. Execution quality

Record signal time, scheduled time, request time, broker acknowledgement, fill time and protection-confirmation time. Calculate entry/exit slippage, latency percentiles, rejection rates, fill-mode performance and missed-window counts. Link every datapoint back to the complete order lifecycle and raw MT5 retcode/comment.

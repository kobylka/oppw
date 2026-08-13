# ADR 0036: Manual tax accounting and after-tax analytics

- Status: Accepted
- Date: 2026-08-13

## Context

Tax charges need to be recorded by an operator because neither MT5 trade profit nor an observed broker balance delta identifies the tax amount and accounting period reliably. Treating tax as a withdrawal would mix tax expense with returned investor capital, reduce net contributions, and inflate the existing capital-adjusted return. Treating a manual accounting charge as a broker-equity movement could also create an artificial drawdown adjustment when no money left the trading account.

## Decision

`account_cash_flows` remains the immutable authority and adds the semantic `TAX` flow type without a schema migration because `flow_type` is already a bounded string column. `cashflow.php` is the sole manual write endpoint. A tax request accepts a non-zero amount in either sign and persists it as a negative amount. Operators should provide a stable `referenceKey`; identical retries are idempotent and conflicting reuse is rejected.

Tax is an accounting charge, not investor capital and not evidence of broker equity movement. It therefore does not change top-ups, withdrawals, net contributions, the broker-equity cash-flow adjustment, or trading drawdown. If broker equity separately changes, the existing `TOP_UP`, `WITHDRAWAL`, or `ADJUSTMENT` authority represents that movement.

Analytics reports the positive tax magnitude, keeps `netProfit` and `capitalAdjustedReturnPercent` as pre-tax trading measures, and additively exposes `afterTaxNetProfit` and `afterTaxCapitalAdjustedReturnPercent`. The Android Analytics screen shows the tax and both capital-adjusted return views. Older backends remain compatible because the Android parser defaults tax to zero and falls back to the corresponding pre-tax profit and return.

## Consequences

- Tax is visible without being mislabeled as a withdrawal or trading loss.
- Pre-tax historical metric meanings remain unchanged.
- A tax plus a real broker withdrawal may legitimately produce two records with different authorities and purposes.
- Backdated manual tax changes invalidate both the completed analytics response and historical cash-flow input segments.
- Cash-flow authority remains online indefinitely and immutable; no forward SQL migration is required for this semantic value.

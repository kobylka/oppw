# ADR 0019: Explicit all-history analytics

- Status: Accepted
- Date: 2026-07-29

## Context

An authenticated analytics denial-of-service risk required bounding query and response work. A fixed 80-week and 160 account-week policy was initially added alongside the actual resource controls, but that policy silently changed valid user requests and prevented the monitoring app from showing complete retained history.

## Decision

Analytics accepts any positive `rolling_weeks` value and the explicit `all_history=1` mode. All-history mode selects every available calendar week between the first and latest trade or equity observation in the permitted account scope. The response reports `filters.allHistory`, `availableWeeks`, and `effectiveRollingWeeks`, and Android provides an **All history** control instead of requiring a magic numeric value.

The denial-of-service boundary remains enforced by authentication, per-device and per-IP rate limits, one in-flight request per device, an eight-account scope limit, bounded filter/trade/lifecycle materialization, and date predicates on every history query. Minute equity work is also bounded by hot retention; older retained history uses the indefinite daily projection. A safety result limit rejects the request rather than silently returning a partial result.

## Consequences

- Demo, Real, or combined account scopes can request every available analytics week.
- A request for 82 weeks remains 82 weeks when that much history exists.
- Full history can take longer than a short rolling window, but duplicate concurrent work from the same device is rejected.
- Numeric and all-history modes are explicit in the API response and Android state.

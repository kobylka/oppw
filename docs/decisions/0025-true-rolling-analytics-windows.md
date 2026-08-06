# ADR 0025: True rolling analytics windows

- Status: Superseded by ADR 0027
- Date: 2026-08-06
- Supersedes: ADR 0019's calendar-week window selection

## Context

The Analytics screen labelled a request as a rolling number of weeks, but the backend expanded the request to whole Europe/Warsaw calendar weeks. Depending on the day and time of the newest observation, a one-week request could include almost two weeks of data and an N-week request could include nearly N+1 weeks.

## Decision

A requested `rolling_weeks=N` now means the trailing `N * 7 * 24 hours` ending at the latest trade or equity observation in the permitted selected-account scope. The API uses a one-millisecond exclusive endpoint, matching MySQL timestamp precision, so the anchor observation is included by existing `[start, end)` SQL predicates. If the requested duration reaches before the first observation, the start is clamped to that first observation. `all_history=1` uses that exact first-to-latest span.

Europe/Warsaw calendar boundaries remain an internal input-cache partitioning optimization only; partial boundary segments are valid and do not change the requested range. The response keeps its existing exact UTC `filterOptions.windowStart` and `windowEndExclusive` fields, which Android now displays.

## Consequences

- The Analytics label and data scope agree: a four-week request contains the last 28 days of selected-account activity.
- `availableWeeks` and `effectiveRollingWeeks` describe trailing seven-day durations, not counted Warsaw calendar weeks.
- Existing cached responses and input segments are versioned separately from the old calendar-window semantics.

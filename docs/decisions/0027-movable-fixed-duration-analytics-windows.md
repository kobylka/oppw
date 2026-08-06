# ADR 0027: Movable fixed-duration analytics windows

- Status: Accepted
- Date: 2026-08-06
- Supersedes: ADR 0025's mandatory latest-observation anchor

## Context

ADR 0025 corrected numeric analytics requests from expanded calendar-week buckets to exact trailing durations, but it still provided only the latest N weeks. Users could choose the duration but could not choose which historical N-week period to analyze. Calling that single latest-period filter a rolling-window selector was incomplete.

## Decision

`rolling_weeks=N` defines a fixed duration of exactly `N * 7 * 24 hours`. With no date parameter, the window defaults to the latest selected-account trade or equity observation. The additive `window_end_date=YYYY-MM-DD` parameter moves the same duration through history. It names the final included Europe/Warsaw calendar date, and the SQL-exclusive boundary is the following local midnight. The date must be within the selected accounts' first and latest available activity dates.

`all_history=1` remains independent, ignores a movable-window date, and returns the complete first-to-latest activity span. Responses echo `filters.windowEndDate` and publish `filterOptions.availableStartDate` and `availableEndDate` so Android can constrain its date picker. Exact UTC `windowStart` and `windowEndExclusive` remain the executed-query authority.

The Android screen defaults a numeric request to the latest N weeks, allows the user to select the inclusive end date, and offers an explicit return to the latest window or all history. The response-cache implementation identity advances because the selected date is part of request identity; completed-week input segments continue to key themselves by their exact UTC boundaries.

## Consequences

- A four-week request can analyze any available historical four-week interval instead of only the latest 28 days.
- Warsaw midnight and daylight-saving transitions are handled by the backend rather than inferred by the mobile client.
- Existing clients remain compatible because omitting the new parameter preserves latest-window behavior and all new response fields are additive.
- No database migration is required.

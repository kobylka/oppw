# OPPW Monitor 14.0.0

## Rolling-week Analytics filter

- Removed the Analytics year filter and its API parameter.
- Added a numeric rolling-week window selected by the user.
- Default requested window: 4 weeks.
- Effective window: the smaller of the requested window and the available calendar history.
- The window is anchored to the latest Monday containing trade data and includes complete Monday-to-Monday calendar weeks.
- The selected window applies server-side to trades, execution lifecycles, cash flows, equity-derived risk metrics, distributions, benchmarks, and drill-down samples.
- Leverage and exit-reason choices are restricted to values present inside the active window.
- The API reports requested weeks, effective weeks, available weeks, and exact UTC window boundaries.
- Stale Analytics responses can no longer overwrite a newer user filter selection.

The class-distribution analysis can still group results by year and leverage; year is no longer a filter.

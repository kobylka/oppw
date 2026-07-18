# OPPW Monitor v9 changelog

## Android

- Individual full cards for all active conditions.
- Routine log checks hidden by default, with an explicit switch to show them.
- `POSITION_OPEN` displayed as `POSITION_IS_OPEN`.
- Sharpe, Sortino, Calmar, Omega, Ulcer Index, daily VaR 95%, and Expected Shortfall 95%.
- Strategy heartbeat and last publisher update shown separately from API reachability.
- Weekend idle phase/regime handling.
- Exact cash-flow dates and deposits-to-date line on the all-time chart.
- Market-only current/previous week and latest-day O/H/L/C.

## Backend

- Publisher heartbeat derived from the latest snapshot timestamp.
- Flat weekends normalized to `WEEKEND IDLE`, `Weekend`, and `None`.
- Capital-adjusted daily risk metrics.
- Friday-started US100 strategy-week aggregation.
- Historical event-name compatibility and routine-log filtering.
- Initial-funding and cash-flow date extrapolation for all-time history.

## MT5 v38

- New monitoring event name `POSITION_IS_OPEN`.
- Weekend phase publication.
- Centered red/green AutoTrading banner after every minute Trade Status.
- No order execution, sizing, protection threshold, entry, exit, or timing rule changed.

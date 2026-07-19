# OPPW v12 changelog

## MT5 continuous loop v43

- Added full flat-account pre-trade What-if ticket.
- Added proposed hard-stop calculations using `-0.5 / leverage`.
- Added MT5-margin, free-margin, margin-level and stress-scenario values.
- Added structured strategy decision recorder with stable IDs and source attribution.
- Added completed-week and previous-trade history recovery for decision inputs.
- Added A/B/C/D classification to every new close event and the last-closed-trade snapshot.
- Updated publisher build/user-agent to v43.

## Backend

- Replaced five-trade gate with a mathematically valid two-observation minimum.
- Annualized closed-trade Sharpe and Sortino using 52 strategy periods.
- Added positive-only Sortino infinity handling.
- Added persistent A/B/C/D columns, historical backfill and database triggers.
- Added class aggregates and full best-to-worst trade distribution.

## Android v12 patch

- Expanded the flat Position screen into a pre-trade ticket.
- Added hard-stop and scenario panels.
- Added strategy decision recorder and publisher-labeled last trade.
- Added annualized ratio labeling and sample count.
- Added Guy Fleury class panel and best-to-worst trade graph.
- Removed the explicit `foundation.layout.weight` import to avoid the earlier internal `RowColumnParentData.weight` compiler error.

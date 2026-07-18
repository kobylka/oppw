# v10 implementation map

| Requirement | Implementation |
|---|---|
| Weekend open position must not show OH countdown | `util/MarketClock.kt`, `ui/screens/OverviewScreen.kt`, `ui/screens/PositionScreen.kt` |
| Time-scaled equity charts | `ui/components/Charts.kt`; x-position is derived from parsed epoch milliseconds |
| Do not repeat closest condition | `ui/screens/PositionScreen.kt`; `sameCondition()` filters the secondary list |
| Closed-trade Sharpe/Sortino | `util/TradeMetrics.kt`, `data/JsonParser.kt`, `ui/screens/AnalyticsScreen.kt` |
| Routine logs hidden by default | `util/LogFilters.kt`, `ui/screens/LogsScreen.kt`; local filtering and `rememberSaveable(accountKey) { false }` |

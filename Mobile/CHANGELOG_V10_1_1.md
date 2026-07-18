# OPPW Monitor Android v10.1.1

- Fixes blank vertical gaps left by locally filtered routine log entries.
- Routine checks are now removed inside `EventsPagingSource` before items reach `LazyColumn`.
- The paging source backfills additional backend pages until it has a full visible page or no older events remain.
- The v9.1 authentication files restored in v10.1 are unchanged.
- All v10 chart, weekend, condition de-duplication and closed-trade Sharpe/Sortino changes are preserved.

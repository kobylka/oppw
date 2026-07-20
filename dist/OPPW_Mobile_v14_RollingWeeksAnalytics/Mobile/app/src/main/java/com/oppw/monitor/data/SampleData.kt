package com.oppw.monitor.data

object SampleData {
    val response = MonitorResponse(
        generatedAt = "2026-07-17T21:15:00+02:00",
        snapshot = MonitorSnapshot(
            connection = ConnectionStatus(true, "2026-07-17T21:15:00+02:00", "OPPW-001", "2026-W29", "OK", "Friday Regular", "Tight stop loss (0.4%)", "CH / TO", "2026-07-17T21:59:57+02:00", 0.3, 0.5, "RUNNING", "2026-07-17T21:15:00+02:00", 0.0, "2026-07-17T21:15:00+02:00"),
            account = AccountStatus("PLN", 30_000.0, 111.12, 30_000.0, 29_632.50),
            position = PositionStatus("US100", "BUY", 0.05, 2127790, "2026-07-16T15:29:57+02:00", 29311.85, 29240.0, 29241.5, "2026-07-17T21:15:00+02:00", "2026-07-17T21:15:00+02:00", "2026-07-17T21:15:00+02:00", 0.3, -367.5, -0.2451, 8.0, -1.9609, 2222.4, 0.075, 29194.6, 0.0, 30777.44, false, "Tight stop loss (0.4%)", "TSL", ""),
            potentialPosition = null,
            closestCondition = PriceCondition("TSL", 29194.6, 29240.0, 45.4, 0.1553, "below", true, "US100"),
            conditions = listOf(PriceCondition("TSL", 29194.6, 29240.0, 45.4, 0.1553, "below", true, "US100")),
            marketStats = MarketStats(null, null),
            equityCurves = EquityCurves(emptyList(), emptyList(), emptyList()),
            equityHistory = emptyList(),
        ),
        eventTypes = listOf("BUY_ACCEPTED", "POSITION_CLOSED"),
    )
}

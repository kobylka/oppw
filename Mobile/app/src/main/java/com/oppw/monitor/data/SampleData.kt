package com.oppw.monitor.data

object SampleData {
    val response = MonitorResponse(
        generatedAt = "2026-07-16T21:15:00+02:00",
        snapshot = MonitorSnapshot(
            connection = ConnectionStatus(true, "2026-07-16T21:15:00+02:00", "OPPW-001", "2026-W29", "OK", "Thursday Regular Session", "CH / TO", "2026-07-16T21:59:57+02:00", 0.3, 0.5),
            account = AccountStatus("PLN", 30_000.0, 111.12, 30_000.0, 29_632.50),
            position = PositionStatus("US100", "BUY", 0.05, 2127790, "2026-07-16T15:29:57+02:00", 29311.85, 29240.0, 29241.5, -367.5, -0.2451, 8.0, -1.9609, 222125.0, 7.4, 29194.6, 0.0, false, "THURSDAY_TIGHT_SL", "TSL1", ""),
            closestCondition = ClosestCondition("TSL1", 29194.6, 45.4, 0.1553, "below"),
            equityHistory = listOf(30000.0, 29940.0, 30120.0, 29880.0, 29632.5).mapIndexed { i, value -> EquityPoint("$i", value) },
        ),
        events = listOf(
            MonitorEvent(1, "2026-07-16T21:14:00+02:00", "INFO", "TSL2", true, "Thursday stop is installed correctly."),
            MonitorEvent(2, "2026-07-16T21:13:00+02:00", "INFO", "CH", false, "Signal price remains below the close target."),
            MonitorEvent(3, "2026-07-16T15:29:57+02:00", "INFO", "POSITION_OPEN", true, "BUY 0.05 US100 @ 29311.85"),
        ),
    )
}

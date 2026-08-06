package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Test

class StatusApiClientTimeoutTest {
    @Test
    fun analyticsUsesLongerReadTimeoutThanSmallApiResponses() {
        assertEquals(30_000, requestReadTimeoutMillis("analytics.php?account=DEMO&rolling_weeks=80"))
        assertEquals(8_000, requestReadTimeoutMillis("status.php?account=DEMO"))
    }

    @Test
    fun analyticsCanRequestExplicitOrCompleteHistory() {
        assertEquals("&rolling_weeks=82", analyticsWindowQuery(AnalyticsFilters(rollingWeeks = 82, allHistory = false)))
        assertEquals(
            "&rolling_weeks=12&window_end_date=2026-05-17",
            analyticsWindowQuery(AnalyticsFilters(rollingWeeks = 12, windowEndDate = "2026-05-17")),
        )
        assertEquals("&rolling_weeks=4", analyticsWindowQuery(AnalyticsFilters()))
        assertEquals(
            "&rolling_weeks=4&all_history=1",
            analyticsWindowQuery(UiState().analyticsFilters.copy(windowEndDate = "2026-05-17")),
        )
    }
}

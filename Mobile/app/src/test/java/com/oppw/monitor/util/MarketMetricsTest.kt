package com.oppw.monitor.util

import com.oppw.monitor.data.MarketWeekStats
import org.junit.Assert.assertEquals
import org.junit.Test

class MarketMetricsTest {
    @Test
    fun latestDayChangesAreDerivedFromDailyOpenInsteadOfWeeklyPercentages() {
        val changes = dailyMarketChanges(stats(
            dailyOpen = 110.0,
            dailyHigh = 112.0,
            dailyLow = 108.0,
            dailyClose = 111.0,
            dailyHighPercent = 12.0,
            dailyLowPercent = 8.0,
            dailyClosePercent = 11.0,
        ))

        assertEquals((112.0 / 110.0 - 1.0) * 100.0, changes.highPercent!!, 0.000001)
        assertEquals((108.0 / 110.0 - 1.0) * 100.0, changes.lowPercent!!, 0.000001)
        assertEquals((111.0 / 110.0 - 1.0) * 100.0, changes.closePercent!!, 0.000001)
    }

    @Test
    fun payloadPercentagesRemainFallbackWhenDailyPricesAreUnavailable() {
        val changes = dailyMarketChanges(stats(
            dailyOpen = null,
            dailyHigh = null,
            dailyLow = null,
            dailyClose = null,
            dailyHighPercent = 1.0,
            dailyLowPercent = -2.0,
            dailyClosePercent = 0.5,
        ))

        assertEquals(1.0, changes.highPercent!!, 0.000001)
        assertEquals(-2.0, changes.lowPercent!!, 0.000001)
        assertEquals(0.5, changes.closePercent!!, 0.000001)
    }

    private fun stats(
        dailyOpen: Double?,
        dailyHigh: Double?,
        dailyLow: Double?,
        dailyClose: Double?,
        dailyHighPercent: Double?,
        dailyLowPercent: Double?,
        dailyClosePercent: Double?,
    ) = MarketWeekStats(
        week = "20 Jul - 26 Jul 2026",
        currentPrice = 111.0,
        weekOpen = 100.0,
        weekOpenDate = "2026-07-20",
        weeklyHigh = 112.0,
        weeklyLow = 99.0,
        weeklyClose = 111.0,
        weeklyHighPercent = 12.0,
        weeklyLowPercent = -1.0,
        weeklyClosePercent = 11.0,
        dailyDate = "2026-07-21",
        dailyOpen = dailyOpen,
        dailyHigh = dailyHigh,
        dailyLow = dailyLow,
        dailyClose = dailyClose,
        dailyHighPercent = dailyHighPercent,
        dailyLowPercent = dailyLowPercent,
        dailyClosePercent = dailyClosePercent,
    )
}

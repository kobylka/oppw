package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EquityBoundariesTest {
    private fun point(time: String, value: Double) = EquityPoint(time, value)

    @Test
    fun removesMondayPointsBeforeCashOpen() {
        val result = weeklyEquityFromMarketOpen(
            listOf(
                point("2026-07-27T09:33:00+02:00", 247311.36),
                point("2026-07-27T15:29:00+02:00", 247311.36),
                point("2026-07-27T15:30:00+02:00", 247276.96),
                point("2026-07-27T15:31:00+02:00", 244942.79),
            ),
            "2026-07-27T15:30:00+02:00",
            null,
        )

        assertEquals(listOf(247276.96, 244942.79), result.map { it.value })
        assertEquals("2026-07-27T15:30:00+02:00", result.first().time)
    }

    @Test
    fun insertsBoundaryWhenDownsamplingSkippedExactCashOpen() {
        val result = weeklyEquityFromMarketOpen(
            listOf(point("2026-07-27T15:31:00+02:00", 244942.79)),
            "2026-07-27T15:30:00+02:00",
            null,
        )

        assertEquals(2, result.size)
        assertEquals("2026-07-27T15:30:00+02:00", result.first().time)
        assertEquals(244942.79, result.first().value, 0.001)
    }

    @Test
    fun manualPreopenPositionUsesItsOpeningTime() {
        val position = position(openedAt = "2026-07-27T14:45:12+02:00", manual = true)
        val result = weeklyEquityFromMarketOpen(
            listOf(
                point("2026-07-27T14:44:00+02:00", 100.0),
                point("2026-07-27T14:46:00+02:00", 101.0),
            ),
            "2026-07-27T15:30:00+02:00",
            position,
        )

        assertEquals("2026-07-27T14:45:12+02:00", result.first().time)
        assertEquals(101.0, result.first().value, 0.001)
    }

    @Test
    fun priorCompletedWeekIsNotFilteredByCurrentWeekBoundary() {
        val original = listOf(
            point("2026-07-20T15:30:00+02:00", 100.0),
            point("2026-07-24T22:00:00+02:00", 110.0),
        )
        assertEquals(
            original,
            weeklyEquityFromMarketOpen(original, "2026-07-27T15:30:00+02:00", null),
        )
    }

    @Test
    fun mondayBeforeCashOpenHasNoWeeklyCurve() {
        val result = weeklyEquityFromMarketOpen(
            listOf(point("2026-07-27T09:33:00+02:00", 100.0)),
            "2026-07-27T15:30:00+02:00",
            null,
        )
        assertTrue(result.isEmpty())
    }

    @Test
    fun holidayWeekUsesFirstTradingDayFromExchangeCalendar() {
        val result = weeklyEquityFromMarketOpen(
            listOf(
                point("2026-09-07T16:00:00+02:00", 100.0),
                point("2026-09-08T15:31:00+02:00", 101.0),
            ),
            "2026-09-08T15:30:00+02:00",
            null,
        )
        assertEquals("2026-09-08T15:30:00+02:00", result.first().time)
        assertEquals(101.0, result.first().value, 0.001)
    }

    @Test
    fun missingAuthoritativeBoundaryLeavesCurveUnchanged() {
        val original =
            listOf(point("2026-07-27T09:33:00+02:00", 100.0))
        val result = weeklyEquityFromMarketOpen(
            original,
            "",
            null,
        )
        assertEquals(original, result)
    }

    private fun position(openedAt: String, manual: Boolean) = PositionStatus(
        symbol = "US100", side = "BUY", volume = 1.0, ticket = 1L,
        openedAt = openedAt, openPrice = 1.0, bid = 1.0, ask = 1.0,
        priceTime = "", bidAt = "", askAt = "", tickAgeSeconds = null,
        profit = 0.0, profitPercent = 0.0, strategyLeverage = 1.0,
        leveragedProfitPercent = 0.0, exposure = 0.0, effectiveLeverage = 1.0,
        stopLoss = 0.0, takeProfit = 0.0, potentialTakeProfit = 0.0,
        breakEvenArmed = false, protectionRegime = "", activeSlReason = "", activeTpReason = "",
        manual = manual,
    )
}

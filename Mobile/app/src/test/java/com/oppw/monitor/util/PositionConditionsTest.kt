package com.oppw.monitor.util

import com.oppw.monitor.data.PriceCondition
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PositionConditionsTest {
    @Test
    fun firstTradingDayHidesBreakEvenCheckAndSelectsNextClosestCondition() {
        val breakEven = condition("BE CHECK", 2.0, "QQQ")
        val stopLoss = condition("SL", 1_500.0, "US100")

        val display = positionConditionDisplay(
            conditions = listOf(breakEven, stopLoss),
            reportedClosest = breakEven,
            ohPending = false,
            snapshotAt = "2026-07-27T16:00:00+02:00",
            weekOpenDate = "2026-07-27",
        )

        assertEquals("SL", display.closest?.name)
        assertEquals(listOf("SL"), display.visible.map { it.name })
        assertTrue(display.others.isEmpty())
    }

    @Test
    fun holidayShiftedFirstTradingDayAlsoHidesBreakEvenCheck() {
        val breakEven = condition("BE CHECK", 2.0, "QQQ")

        val display = positionConditionDisplay(
            conditions = listOf(breakEven),
            reportedClosest = breakEven,
            ohPending = false,
            snapshotAt = "2026-09-08T16:00:00+02:00",
            weekOpenDate = "2026-09-08",
        )

        assertTrue(display.visible.isEmpty())
        assertEquals(null, display.closest)
    }

    @Test
    fun mondayFallbackHidesBreakEvenCheckWhenWeekOpenDateIsUnavailable() {
        val breakEven = condition("BE CHECK", 2.0, "QQQ")

        val display = positionConditionDisplay(
            conditions = listOf(breakEven),
            reportedClosest = breakEven,
            ohPending = false,
            snapshotAt = "2026-07-27T16:00:00+02:00",
            weekOpenDate = "",
        )

        assertTrue(display.visible.isEmpty())
        assertEquals(null, display.closest)
    }

    @Test
    fun laterTradingDayKeepsBreakEvenCheck() {
        val breakEven = condition("BE CHECK", 2.0, "QQQ")

        val display = positionConditionDisplay(
            conditions = listOf(breakEven),
            reportedClosest = breakEven,
            ohPending = false,
            snapshotAt = "2026-07-28T16:00:00+02:00",
            weekOpenDate = "2026-07-27",
        )

        assertFalse(display.visible.isEmpty())
        assertEquals("BE CHECK", display.closest?.name)
    }

    private fun condition(name: String, distancePoints: Double, source: String) = PriceCondition(
        name = name,
        targetPrice = 100.0,
        currentPrice = 101.0,
        distancePoints = distancePoints,
        distancePercent = 1.0,
        direction = "below",
        active = true,
        source = source,
    )
}

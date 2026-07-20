package com.oppw.monitor.util

import com.oppw.monitor.data.EquityPoint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TimelineTest {
    @Test
    fun xCoordinatesRepresentElapsedTime() {
        val timeline = equityTimeline(listOf(
            EquityPoint("2026-07-13T15:30:00+02:00", 1.0),
            EquityPoint("2026-07-14T09:00:00+02:00", 2.0),
            EquityPoint("2026-07-14T15:30:00+02:00", 3.0),
            EquityPoint("2026-07-15T15:30:00+02:00", 4.0),
        ))
        assertEquals(0f, timeline.first().xFraction)
        assertEquals(1f, timeline.last().xFraction)
        assertTrue(timeline[2].xFraction in 0.49f..0.51f)
    }
}

package com.oppw.monitor.util

import com.oppw.monitor.data.DrawdownPoint
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DrawdownMetricsTest {
    @Test
    fun identifiesCompletedAndOngoingDrawdownsWithLengthsAndDepths() {
        val result = drawdownStatistics(listOf(
            point(1, "2026-07-01T12:00:00Z", 0.0),
            point(2, "2026-07-02T12:00:00Z", -2.0),
            point(3, "2026-07-05T12:00:00Z", -5.0),
            point(4, "2026-07-10T12:00:00Z", -1.0),
            point(5, "2026-07-20T12:00:00Z", 0.0),
            point(6, "2026-07-25T12:00:00Z", 0.0),
            point(7, "2026-07-26T12:00:00Z", -1.0),
            point(8, "2026-08-02T12:00:00Z", -3.0),
        ))

        assertEquals(2, result.episodes.size)
        result.episodes[0].let { episode ->
            assertEquals(5.0, episode.depthPercent, 0.000001)
            assertTrue(episode.recovered)
            assertEquals("2026-07-01T12:00:00Z", episode.startAt)
            assertEquals(19 * 86_400L, episode.elapsedSeconds)
            assertEquals(15 * 86_400L, episode.recoverySeconds)
            assertEquals(listOf("DEMO:1", "DEMO:2", "DEMO:3", "DEMO:4", "DEMO:5"), episode.tradeKeys)
        }
        result.episodes[1].let { episode ->
            assertEquals(3.0, episode.depthPercent, 0.000001)
            assertEquals("2026-07-25T12:00:00Z", episode.startAt)
            assertEquals(8 * 86_400L, episode.elapsedSeconds)
            assertEquals(null, episode.recoverySeconds)
            assertFalse(episode.recovered)
        }

        assertEquals(4.0, result.averageDepthPercent, 0.000001)
        assertEquals(13.5 * 86_400.0, result.averageLengthSeconds, 0.000001)
        assertEquals(19 * 86_400L, result.longestLengthSeconds)
        assertEquals(15 * 86_400.0, result.averageTroughRecoverySeconds, 0.000001)
        assertEquals(27.0 / 32.0 * 100.0, result.timeUnderwaterPercent, 0.000001)
    }

    @Test
    fun emptySeriesProducesZeroMetrics() {
        assertEquals(DrawdownStatistics(), drawdownStatistics(emptyList()))
    }

    @Test
    fun durationUsesAbsoluteWallClockDifference() {
        val result = drawdownStatistics(listOf(
            point(1, "2026-08-10T12:00:00Z", 0.0),
            point(2, "2026-08-09T12:00:00Z", -2.0),
            point(3, "2026-08-05T12:00:00Z", 0.0),
        ))

        assertEquals(5 * 86_400L, result.episodes.single().elapsedSeconds)
        assertEquals(4 * 86_400L, result.episodes.single().recoverySeconds)
    }

    private fun point(index: Int, closedAt: String, drawdown: Double) = DrawdownPoint(
        index = index,
        tradeKey = "DEMO:$index",
        closedAt = closedAt,
        equityIndex = 100.0 + drawdown,
        drawdownPercent = drawdown,
        maePercent = 0.0,
    )
}

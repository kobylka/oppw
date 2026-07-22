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
            point(1, 0.0),
            point(2, -2.0),
            point(3, -5.0),
            point(4, -1.0),
            point(5, 0.0),
            point(6, -1.0),
            point(7, -3.0),
        ))

        assertEquals(2, result.episodes.size)
        result.episodes[0].let { episode ->
            assertEquals(5.0, episode.depthPercent, 0.000001)
            assertEquals(4, episode.lengthTrades)
            assertEquals(2, episode.recoveryTrades)
            assertTrue(episode.recovered)
            assertEquals(3 * 86_400L, episode.elapsedSeconds)
            assertEquals(listOf("DEMO:2", "DEMO:3", "DEMO:4", "DEMO:5"), episode.tradeKeys)
        }
        result.episodes[1].let { episode ->
            assertEquals(3.0, episode.depthPercent, 0.000001)
            assertEquals(2, episode.lengthTrades)
            assertEquals(null, episode.recoveryTrades)
            assertFalse(episode.recovered)
        }

        assertEquals(4.0, result.averageDepthPercent, 0.000001)
        assertEquals(3.0, result.averageLengthTrades, 0.000001)
        assertEquals(4, result.longestLengthTrades)
        assertEquals(2.0, result.averageRecoveryTrades, 0.000001)
        assertEquals(4.0 / 6.0 * 100.0, result.timeUnderwaterPercent, 0.000001)
    }

    @Test
    fun emptySeriesProducesZeroMetrics() {
        assertEquals(DrawdownStatistics(), drawdownStatistics(emptyList()))
    }

    private fun point(index: Int, drawdown: Double) = DrawdownPoint(
        index = index,
        tradeKey = "DEMO:$index",
        closedAt = "2026-07-${index.toString().padStart(2, '0')}T12:00:00Z",
        equityIndex = 100.0 + drawdown,
        drawdownPercent = drawdown,
        maePercent = 0.0,
    )
}

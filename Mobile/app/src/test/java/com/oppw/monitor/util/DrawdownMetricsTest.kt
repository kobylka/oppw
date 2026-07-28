package com.oppw.monitor.util

import com.oppw.monitor.data.DrawdownAnalytics
import com.oppw.monitor.data.DrawdownEpisodeAnalytics
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
        assertEquals(2, result.episodeCount)
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

    @Test
    fun usesExactBackendMinuteStatisticsWhenChartSeriesWasDownsampled() {
        val result = drawdownStatistics(DrawdownAnalytics(
            maxDrawdownPercent = 12.5,
            averageDepthPercent = 7.25,
            averageLengthSeconds = 5400.0,
            longestLengthSeconds = 86_400L,
            averageTroughRecoverySeconds = 1800.0,
            timeUnderwaterPercent = 62.5,
            statisticsExact = true,
            sampleCount = 10_000,
            seriesDownsampled = true,
            series = listOf(
                point(1, "2026-07-01T10:00:00Z", 0.0),
                point(10_000, "2026-07-02T10:00:00Z", -1.0),
            ),
            episodes = listOf(DrawdownEpisodeAnalytics(
                number = 1,
                startAt = "2026-07-01T10:00:00Z",
                troughAt = "2026-07-01T10:30:00Z",
                endAt = "2026-07-02T10:00:00Z",
                depthPercent = 12.5,
                recovered = true,
                elapsedSeconds = 86_400L,
                recoverySeconds = 84_600L,
                tradeKeys = listOf("DEMO:42"),
            )),
        ))

        assertEquals(7.25, result.averageDepthPercent, 0.000001)
        assertEquals(5400.0, result.averageLengthSeconds, 0.000001)
        assertEquals(86_400L, result.longestLengthSeconds)
        assertEquals(62.5, result.timeUnderwaterPercent, 0.000001)
        assertEquals(listOf("DEMO:42"), result.episodes.single().tradeKeys)
    }

    @Test
    fun filtersLegacySeriesEpisodesShorterThan24HoursWithoutChangingAggregates() {
        val result = drawdownStatistics(listOf(
            point(1, "2026-07-01T00:00:00Z", 0.0),
            point(2, "2026-07-01T01:00:00Z", -2.0),
            point(3, "2026-07-01T02:00:00Z", 0.0),
            point(4, "2026-07-02T00:00:00Z", 0.0),
            point(5, "2026-07-02T01:00:00Z", -3.0),
            point(6, "2026-07-03T00:00:00Z", 0.0),
        ))

        assertEquals(2, result.episodeCount)
        assertEquals(1, result.episodes.size)
        assertEquals(2, result.episodes.single().number)
        assertEquals(86_400L, result.episodes.single().elapsedSeconds)
        assertEquals(2.5, result.averageDepthPercent, 0.000001)
        assertEquals(13.0 * 3600.0, result.averageLengthSeconds, 0.000001)
        assertEquals(86_400L, result.longestLengthSeconds)
    }

    @Test
    fun filtersShortEpisodesFromAnOlderExactBackendResponse() {
        val result = drawdownStatistics(DrawdownAnalytics(
            averageDepthPercent = 3.5,
            averageLengthSeconds = 45_000.0,
            longestLengthSeconds = 86_400L,
            statisticsExact = true,
            episodes = listOf(
                DrawdownEpisodeAnalytics(
                    number = 1,
                    startAt = "2026-07-01T00:00:00Z",
                    troughAt = "2026-07-01T00:30:00Z",
                    endAt = "2026-07-01T01:00:00Z",
                    depthPercent = 2.0,
                    recovered = true,
                    elapsedSeconds = 3600L,
                    recoverySeconds = 1800L,
                    tradeKeys = listOf("DEMO:1"),
                ),
                DrawdownEpisodeAnalytics(
                    number = 2,
                    startAt = "2026-07-02T00:00:00Z",
                    troughAt = "2026-07-02T01:00:00Z",
                    endAt = "2026-07-03T00:00:00Z",
                    depthPercent = 5.0,
                    recovered = true,
                    elapsedSeconds = 86_400L,
                    recoverySeconds = 82_800L,
                    tradeKeys = listOf("DEMO:2"),
                ),
            ),
        ))

        assertEquals(2, result.episodeCount)
        assertEquals(listOf("DEMO:2"), result.episodes.single().tradeKeys)
        assertEquals(3.5, result.averageDepthPercent, 0.000001)
        assertEquals(45_000.0, result.averageLengthSeconds, 0.000001)
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

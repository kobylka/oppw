package com.oppw.monitor.util

import com.oppw.monitor.data.DrawdownAnalytics
import com.oppw.monitor.data.DrawdownPoint
import java.time.Instant
import java.time.OffsetDateTime
import kotlin.math.abs

data class DrawdownEpisode(
    val number: Int,
    val startAt: String,
    val troughAt: String,
    val endAt: String,
    val depthPercent: Double,
    val recovered: Boolean,
    val elapsedSeconds: Long,
    val recoverySeconds: Long?,
    val tradeKeys: List<String>,
)

data class DrawdownStatistics(
    val episodes: List<DrawdownEpisode> = emptyList(),
    val episodeCount: Int = 0,
    val averageDepthPercent: Double = 0.0,
    val averageLengthSeconds: Double = 0.0,
    val longestLengthSeconds: Long = 0L,
    val averageTroughRecoverySeconds: Double = 0.0,
    val timeUnderwaterPercent: Double = 0.0,
)

fun drawdownStatistics(series: List<DrawdownPoint>): DrawdownStatistics {
    if (series.isEmpty()) return DrawdownStatistics()

    val ordered = series.sortedWith(compareBy<DrawdownPoint> { it.index }.thenBy { it.capturedAt })
    val allEpisodes = mutableListOf<DrawdownEpisode>()
    var startIndex: Int? = null
    var troughIndex = -1

    fun closeEpisode(endIndex: Int, recovered: Boolean) {
        val start = startIndex ?: return
        val trough = ordered[troughIndex]
        val end = ordered[endIndex]
        val startEpoch = parseDrawdownEpoch(ordered[start].capturedAt)
        val troughEpoch = parseDrawdownEpoch(trough.capturedAt)
        val endEpoch = parseDrawdownEpoch(end.capturedAt)
        val elapsedSeconds = absoluteSeconds(startEpoch, endEpoch)
        allEpisodes += DrawdownEpisode(
            number = allEpisodes.size + 1,
            startAt = ordered[start].capturedAt,
            troughAt = trough.capturedAt,
            endAt = end.capturedAt,
            depthPercent = -trough.drawdownPercent.coerceAtMost(0.0),
            recovered = recovered,
            elapsedSeconds = elapsedSeconds,
            recoverySeconds = if (recovered) absoluteSeconds(troughEpoch, endEpoch) else null,
            tradeKeys = ordered.subList(start, endIndex + 1)
                .flatMap { point -> point.tradeKeys.ifEmpty { listOf(point.tradeKey) } }
                .filter(String::isNotBlank)
                .distinct(),
        )
        startIndex = null
        troughIndex = -1
    }

    ordered.forEachIndexed { index, point ->
        if (point.drawdownPercent < -DRAWDOWN_EPSILON) {
            if (startIndex == null) {
                startIndex = (index - 1).coerceAtLeast(0)
                troughIndex = index
            } else if (point.drawdownPercent < ordered[troughIndex].drawdownPercent) {
                troughIndex = index
            }
        } else if (startIndex != null) {
            closeEpisode(index, recovered = true)
        }
    }
    if (startIndex != null) closeEpisode(ordered.lastIndex, recovered = false)

    val completedRecoveries = allEpisodes.mapNotNull { it.recoverySeconds }
    val firstEpoch = parseDrawdownEpoch(ordered.first().capturedAt)
    val lastEpoch = parseDrawdownEpoch(ordered.last().capturedAt)
    val observedSeconds = absoluteSeconds(firstEpoch, lastEpoch)
    val timeUnderwaterPercent = if (observedSeconds > 0L) {
        allEpisodes.sumOf { it.elapsedSeconds }.toDouble() / observedSeconds.toDouble() * 100.0
    } else {
        ordered.count { it.drawdownPercent < -DRAWDOWN_EPSILON }.toDouble() / ordered.size * 100.0
    }
    return DrawdownStatistics(
        episodes = allEpisodes.filter { it.elapsedSeconds >= DRAWDOWN_EPISODE_MINIMUM_SECONDS },
        episodeCount = allEpisodes.size,
        averageDepthPercent = allEpisodes.map { it.depthPercent }.averageOrZero(),
        averageLengthSeconds = allEpisodes.map { it.elapsedSeconds.toDouble() }.averageOrZero(),
        longestLengthSeconds = allEpisodes.maxOfOrNull { it.elapsedSeconds } ?: 0L,
        averageTroughRecoverySeconds = completedRecoveries.map(Long::toDouble).averageOrZero(),
        timeUnderwaterPercent = timeUnderwaterPercent,
    )
}

fun drawdownStatistics(drawdown: DrawdownAnalytics): DrawdownStatistics {
    if (!drawdown.statisticsExact) return drawdownStatistics(drawdown.series)
    val minimumSeconds = drawdown.episodeMinimumSeconds.coerceAtLeast(DRAWDOWN_EPISODE_MINIMUM_SECONDS)
    return DrawdownStatistics(
        episodes = drawdown.episodes.map { episode -> DrawdownEpisode(
            number = episode.number,
            startAt = episode.startAt,
            troughAt = episode.troughAt,
            endAt = episode.endAt,
            depthPercent = episode.depthPercent,
            recovered = episode.recovered,
            elapsedSeconds = episode.elapsedSeconds,
            recoverySeconds = episode.recoverySeconds,
            tradeKeys = episode.tradeKeys,
        ) }.filter { it.elapsedSeconds >= minimumSeconds },
        episodeCount = maxOf(drawdown.episodeCount, drawdown.episodes.size),
        averageDepthPercent = drawdown.averageDepthPercent,
        averageLengthSeconds = drawdown.averageLengthSeconds,
        longestLengthSeconds = drawdown.longestLengthSeconds,
        averageTroughRecoverySeconds = drawdown.averageTroughRecoverySeconds,
        timeUnderwaterPercent = drawdown.timeUnderwaterPercent,
    )
}

private fun parseDrawdownEpoch(value: String): Long? =
    runCatching { OffsetDateTime.parse(value).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { Instant.parse(value).toEpochMilli() }.getOrNull()

private fun absoluteSeconds(startEpoch: Long?, endEpoch: Long?): Long =
    if (startEpoch != null && endEpoch != null) abs(endEpoch - startEpoch) / 1_000L else 0L

private fun List<Double>.averageOrZero(): Double = if (isEmpty()) 0.0 else average()

const val DRAWDOWN_EPISODE_MINIMUM_SECONDS = 86_400L
private const val DRAWDOWN_EPSILON = 1e-9

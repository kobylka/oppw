package com.oppw.monitor.util

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
    val averageDepthPercent: Double = 0.0,
    val averageLengthSeconds: Double = 0.0,
    val longestLengthSeconds: Long = 0L,
    val averageTroughRecoverySeconds: Double = 0.0,
    val timeUnderwaterPercent: Double = 0.0,
)

fun drawdownStatistics(series: List<DrawdownPoint>): DrawdownStatistics {
    if (series.isEmpty()) return DrawdownStatistics()

    val ordered = series.sortedWith(compareBy<DrawdownPoint> { it.index }.thenBy { it.closedAt })
    val episodes = mutableListOf<DrawdownEpisode>()
    var startIndex: Int? = null
    var troughIndex = -1

    fun closeEpisode(endIndex: Int, recovered: Boolean) {
        val start = startIndex ?: return
        val trough = ordered[troughIndex]
        val end = ordered[endIndex]
        val startEpoch = parseDrawdownEpoch(ordered[start].closedAt)
        val troughEpoch = parseDrawdownEpoch(trough.closedAt)
        val endEpoch = parseDrawdownEpoch(end.closedAt)
        val elapsedSeconds = absoluteSeconds(startEpoch, endEpoch)
        episodes += DrawdownEpisode(
            number = episodes.size + 1,
            startAt = ordered[start].closedAt,
            troughAt = trough.closedAt,
            endAt = end.closedAt,
            depthPercent = -trough.drawdownPercent.coerceAtMost(0.0),
            recovered = recovered,
            elapsedSeconds = elapsedSeconds,
            recoverySeconds = if (recovered) absoluteSeconds(troughEpoch, endEpoch) else null,
            tradeKeys = ordered.subList(start, endIndex + 1).map { it.tradeKey }.filter(String::isNotBlank).distinct(),
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

    val completedRecoveries = episodes.mapNotNull { it.recoverySeconds }
    val firstEpoch = parseDrawdownEpoch(ordered.first().closedAt)
    val lastEpoch = parseDrawdownEpoch(ordered.last().closedAt)
    val observedSeconds = absoluteSeconds(firstEpoch, lastEpoch)
    val timeUnderwaterPercent = if (observedSeconds > 0L) {
        episodes.sumOf { it.elapsedSeconds }.toDouble() / observedSeconds.toDouble() * 100.0
    } else {
        ordered.count { it.drawdownPercent < -DRAWDOWN_EPSILON }.toDouble() / ordered.size * 100.0
    }
    return DrawdownStatistics(
        episodes = episodes,
        averageDepthPercent = episodes.map { it.depthPercent }.averageOrZero(),
        averageLengthSeconds = episodes.map { it.elapsedSeconds.toDouble() }.averageOrZero(),
        longestLengthSeconds = episodes.maxOfOrNull { it.elapsedSeconds } ?: 0L,
        averageTroughRecoverySeconds = completedRecoveries.map(Long::toDouble).averageOrZero(),
        timeUnderwaterPercent = timeUnderwaterPercent,
    )
}

private fun parseDrawdownEpoch(value: String): Long? =
    runCatching { OffsetDateTime.parse(value).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { Instant.parse(value).toEpochMilli() }.getOrNull()

private fun absoluteSeconds(startEpoch: Long?, endEpoch: Long?): Long =
    if (startEpoch != null && endEpoch != null) abs(endEpoch - startEpoch) / 1_000L else 0L

private fun List<Double>.averageOrZero(): Double = if (isEmpty()) 0.0 else average()

private const val DRAWDOWN_EPSILON = 1e-9

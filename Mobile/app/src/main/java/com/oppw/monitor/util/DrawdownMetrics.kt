package com.oppw.monitor.util

import com.oppw.monitor.data.DrawdownPoint
import java.time.Instant
import java.time.OffsetDateTime

data class DrawdownEpisode(
    val number: Int,
    val startAt: String,
    val troughAt: String,
    val endAt: String,
    val depthPercent: Double,
    val lengthTrades: Int,
    val recoveryTrades: Int?,
    val recovered: Boolean,
    val elapsedSeconds: Long,
    val tradeKeys: List<String>,
)

data class DrawdownStatistics(
    val episodes: List<DrawdownEpisode> = emptyList(),
    val averageDepthPercent: Double = 0.0,
    val averageLengthTrades: Double = 0.0,
    val longestLengthTrades: Int = 0,
    val averageRecoveryTrades: Double = 0.0,
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
        val endEpoch = parseDrawdownEpoch(end.closedAt)
        episodes += DrawdownEpisode(
            number = episodes.size + 1,
            startAt = ordered[start].closedAt,
            troughAt = trough.closedAt,
            endAt = end.closedAt,
            depthPercent = -trough.drawdownPercent.coerceAtMost(0.0),
            lengthTrades = endIndex - start + 1,
            recoveryTrades = if (recovered) endIndex - troughIndex else null,
            recovered = recovered,
            elapsedSeconds = if (startEpoch != null && endEpoch != null) ((endEpoch - startEpoch) / 1_000L).coerceAtLeast(0L) else 0L,
            tradeKeys = ordered.subList(start, endIndex + 1).map { it.tradeKey }.filter(String::isNotBlank).distinct(),
        )
        startIndex = null
        troughIndex = -1
    }

    ordered.forEachIndexed { index, point ->
        if (point.drawdownPercent < -DRAWDOWN_EPSILON) {
            if (startIndex == null) {
                startIndex = index
                troughIndex = index
            } else if (point.drawdownPercent < ordered[troughIndex].drawdownPercent) {
                troughIndex = index
            }
        } else if (startIndex != null) {
            closeEpisode(index, recovered = true)
        }
    }
    if (startIndex != null) closeEpisode(ordered.lastIndex, recovered = false)

    val completedRecoveries = episodes.mapNotNull { it.recoveryTrades }
    val firstEpoch = parseDrawdownEpoch(ordered.first().closedAt)
    val lastEpoch = parseDrawdownEpoch(ordered.last().closedAt)
    val observedSeconds = if (firstEpoch != null && lastEpoch != null) (lastEpoch - firstEpoch) / 1_000L else 0L
    val timeUnderwaterPercent = if (observedSeconds > 0L) {
        episodes.sumOf { it.elapsedSeconds }.toDouble() / observedSeconds.toDouble() * 100.0
    } else {
        ordered.count { it.drawdownPercent < -DRAWDOWN_EPSILON }.toDouble() / ordered.size * 100.0
    }
    return DrawdownStatistics(
        episodes = episodes,
        averageDepthPercent = episodes.map { it.depthPercent }.averageOrZero(),
        averageLengthTrades = episodes.map { it.lengthTrades.toDouble() }.averageOrZero(),
        longestLengthTrades = episodes.maxOfOrNull { it.lengthTrades } ?: 0,
        averageRecoveryTrades = completedRecoveries.map(Int::toDouble).averageOrZero(),
        timeUnderwaterPercent = timeUnderwaterPercent,
    )
}

private fun parseDrawdownEpoch(value: String): Long? =
    runCatching { OffsetDateTime.parse(value).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { Instant.parse(value).toEpochMilli() }.getOrNull()

private fun List<Double>.averageOrZero(): Double = if (isEmpty()) 0.0 else average()

private const val DRAWDOWN_EPSILON = 1e-9

package com.oppw.monitor.util

import com.oppw.monitor.data.EquityPoint
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

data class TimelinePoint(val point: EquityPoint, val xFraction: Float)

private val warsawZone = ZoneId.of("Europe/Warsaw")
private val sqlDateTime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

fun equityTimeline(points: List<EquityPoint>): List<TimelinePoint> {
    if (points.isEmpty()) return emptyList()
    val parsed = points.map { point -> point to parseEpochMillis(point.time) }
    if (parsed.all { it.second != null }) {
        val sorted = parsed.sortedBy { it.second }
        val first = sorted.first().second!!
        val last = sorted.last().second!!
        val span = last - first
        if (span > 0L) return sorted.map { (point, epoch) -> TimelinePoint(point, ((epoch!! - first).toDouble() / span.toDouble()).toFloat()) }
    }
    val denominator = points.lastIndex.coerceAtLeast(1).toFloat()
    return points.mapIndexed { index, point -> TimelinePoint(point, if (points.size == 1) 0.5f else index / denominator) }
}

private fun parseEpochMillis(value: String): Long? {
    val text = value.trim()
    if (text.isEmpty()) return null
    return runCatching { OffsetDateTime.parse(text).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { Instant.parse(text).toEpochMilli() }.getOrNull()
        ?: runCatching { LocalDateTime.parse(text, sqlDateTime).atZone(warsawZone).toInstant().toEpochMilli() }.getOrNull()
        ?: runCatching { LocalDate.parse(text).atStartOfDay(warsawZone).toInstant().toEpochMilli() }.getOrNull()
}

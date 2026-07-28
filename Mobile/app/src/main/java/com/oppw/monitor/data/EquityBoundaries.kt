package com.oppw.monitor.data

import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.IsoFields

private val equityWarsawZone = ZoneId.of("Europe/Warsaw")
private val equitySqlDateTime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

internal fun weeklyEquityFromMarketOpen(
    points: List<EquityPoint>,
    publishedWeekCashOpen: String,
    position: PositionStatus?,
): List<EquityPoint> {
    if (points.isEmpty()) return points

    val publishedOpen = parseEquityTime(publishedWeekCashOpen)
    val regularOpen = publishedOpen ?: return points

    val opened = position?.takeIf { it.manual }?.openedAt?.let(::parseEquityTime)
    val usesManualOpen =
        opened != null &&
        opened.toInstant().isBefore(regularOpen.toInstant()) &&
        opened.withZoneSameInstant(regularOpen.zone).toLocalDate() == regularOpen.toLocalDate()
    val boundary = if (usesManualOpen) opened else regularOpen
    val boundaryText = if (usesManualOpen) position.openedAt else publishedWeekCashOpen.trim()

    val parsed = points.mapNotNull { point -> parseEquityTime(point.time)?.let { point to it } }
    if (parsed.isEmpty()) return points

    // A weekend response can intentionally contain the completed prior week. Only
    // apply the current boundary when the response contains points from its ISO week.
    if (parsed.none { (_, time) -> sameIsoWeek(time, boundary) }) return points

    val retained = parsed
        .filter { (_, time) -> !time.toInstant().isBefore(boundary.toInstant()) }
        .sortedBy { (_, time) -> time.toInstant() }
        .map { it.first }
    if (retained.isEmpty()) return emptyList()

    val firstTime = parseEquityTime(retained.first().time) ?: return retained
    return if (firstTime.toInstant().isAfter(boundary.toInstant())) {
        listOf(retained.first().copy(time = boundaryText)) + retained
    } else retained
}

private fun parseEquityTime(value: String): java.time.ZonedDateTime? {
    val text = value.trim()
    if (text.isEmpty()) return null
    return runCatching { OffsetDateTime.parse(text).toZonedDateTime() }.getOrNull()
        ?: runCatching { Instant.parse(text).atZone(equityWarsawZone) }.getOrNull()
        ?: runCatching { LocalDateTime.parse(text, equitySqlDateTime).atZone(equityWarsawZone) }.getOrNull()
}

private fun sameIsoWeek(left: java.time.ZonedDateTime, right: java.time.ZonedDateTime): Boolean {
    val leftDate = left.withZoneSameInstant(right.zone).toLocalDate()
    val rightDate = right.toLocalDate()
    return leftDate.get(IsoFields.WEEK_BASED_YEAR) == rightDate.get(IsoFields.WEEK_BASED_YEAR) &&
        leftDate.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR) == rightDate.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR)
}

package com.oppw.monitor.util

import com.oppw.monitor.data.PriceCondition
import java.time.DayOfWeek
import java.time.LocalDate
import kotlin.math.abs

data class PositionConditionDisplay(
    val visible: List<PriceCondition>,
    val closest: PriceCondition?,
    val others: List<PriceCondition>,
)

fun positionConditionDisplay(
    conditions: List<PriceCondition>,
    reportedClosest: PriceCondition?,
    ohPending: Boolean,
    snapshotAt: String,
    weekOpenDate: String,
): PositionConditionDisplay {
    val firstTradingDay = isFirstTradingDay(snapshotAt, weekOpenDate)
    fun hidden(condition: PriceCondition): Boolean =
        condition.name.equals("OH", true) && !ohPending ||
            condition.name.equals("BE CHECK", true) && firstTradingDay

    val visible = conditions.filterNot(::hidden).sortedBy { it.distancePoints }
    val closest = reportedClosest?.takeUnless(::hidden) ?: visible.firstOrNull()
    return PositionConditionDisplay(
        visible = visible,
        closest = closest,
        others = visible.filterNot { sameCondition(it, closest) },
    )
}

private fun isFirstTradingDay(snapshotAt: String, weekOpenDate: String): Boolean {
    val snapshotDate = parseIsoDate(snapshotAt) ?: return false
    val firstSessionDate = parseIsoDate(weekOpenDate)
    return firstSessionDate?.let { snapshotDate == it } ?: (snapshotDate.dayOfWeek == DayOfWeek.MONDAY)
}

private fun parseIsoDate(value: String): LocalDate? = runCatching {
    LocalDate.parse(value.trim().take(10))
}.getOrNull()

private fun sameCondition(first: PriceCondition, second: PriceCondition?): Boolean {
    if (second == null) return false
    return first.name.equals(second.name, true) &&
        first.source.equals(second.source, true) &&
        abs(first.targetPrice - second.targetPrice) <= 1e-6
}

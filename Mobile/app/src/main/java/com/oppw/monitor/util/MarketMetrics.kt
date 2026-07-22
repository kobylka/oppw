package com.oppw.monitor.util

import com.oppw.monitor.data.MarketWeekStats

data class DailyMarketChanges(
    val highPercent: Double?,
    val lowPercent: Double?,
    val closePercent: Double?,
)

fun dailyMarketChanges(stats: MarketWeekStats): DailyMarketChanges = DailyMarketChanges(
    highPercent = dailyChange(stats.dailyOpen, stats.dailyHigh) ?: stats.dailyHighPercent,
    lowPercent = dailyChange(stats.dailyOpen, stats.dailyLow) ?: stats.dailyLowPercent,
    closePercent = dailyChange(stats.dailyOpen, stats.dailyClose) ?: stats.dailyClosePercent,
)

private fun dailyChange(open: Double?, value: Double?): Double? =
    if (open != null && open > 0.0 && value != null) (value / open - 1.0) * 100.0 else null

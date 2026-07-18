package com.oppw.monitor.util

import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId

object MarketClock {
    private val zone = ZoneId.of("Europe/Warsaw")
    fun isWeekend(nowEpochMs: Long): Boolean {
        val day = Instant.ofEpochMilli(nowEpochMs).atZone(zone).dayOfWeek
        return day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY
    }
}

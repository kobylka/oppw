package com.oppw.monitor.util

import com.oppw.monitor.data.MonitorEvent

fun isRoutineEvent(event: MonitorEvent): Boolean {
    val name = event.name.trim().uppercase()
    if (name in ROUTINE_NAMES) return true
    if (name.startsWith("TSL") || name.startsWith("CONDITION_REPORT")) return true
    if (name.startsWith("SCHEDULED_CHECK")) return true
    val message = event.message.uppercase()
    return message.startsWith("CHECK ") || message.contains("CONDITION_REPORT_BEGIN") || message.contains("CONDITION_REPORT_END")
}


private val ROUTINE_NAMES = setOf(
    "POSITION_OPEN", "POSITION_IS_OPEN", "ENTRY_SIGNAL_OPEN_AVAILABLE", "EXIT_LATCH_CLEAR",
    "CURRENT_M1_AVAILABLE", "NEW_WEEK_ENTRY", "BUY_TIME_REACHED", "ENTRY_EXECUTION_WINDOW_OPEN",
    "ENTRY_PENDING_CLEAR", "FRESH_TRADE_TICK", "BUY_ELIGIBLE", "OPEN_MINUS_3_REACHED",
    "CLOSE_MINUS_3_REACHED", "OH", "CH", "TO", "SL", "BH", "BE", "BEO", "BEPRE",
)

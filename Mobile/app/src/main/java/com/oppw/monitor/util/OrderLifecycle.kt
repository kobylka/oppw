package com.oppw.monitor.util

val expectedOrderLifecycleStages = listOf(
    "SIGNAL", "DECISION", "CHECKED", "SENT", "ACCEPTED", "FILLED",
    "POSITION_VISIBLE", "PROTECTED", "MODIFIED",
    "EXIT_CHECKED", "EXIT_SENT", "EXIT_ACCEPTED", "EXIT_FILLED",
    "CLOSED", "PUBLISHED", "MOBILE_RECEIPT",
)

private val executorMarketExitStages = setOf("EXIT_CHECKED", "EXIT_SENT", "EXIT_ACCEPTED")

fun isBrokerManagedExit(observedStages: Set<String>): Boolean =
    "CLOSED" in observedStages && executorMarketExitStages.none(observedStages::contains)

fun lifecycleAbsentStageLabel(stage: String, observedStages: Set<String>): String =
    if (stage in executorMarketExitStages && isBrokerManagedExit(observedStages)) {
        "N/A · broker-managed exit"
    } else {
        "—"
    }

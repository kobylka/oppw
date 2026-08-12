package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OrderLifecycleTest {
    @Test
    fun brokerProtectionExitMarksExecutorSellStagesNotApplicable() {
        val observed = setOf("FILLED", "POSITION_VISIBLE", "PROTECTED", "EXIT_FILLED", "CLOSED")

        assertTrue(isBrokerManagedExit(observed))
        assertEquals("N/A · broker-managed exit", lifecycleAbsentStageLabel("EXIT_CHECKED", observed))
        assertEquals("N/A · broker-managed exit", lifecycleAbsentStageLabel("EXIT_SENT", observed))
        assertEquals("N/A · broker-managed exit", lifecycleAbsentStageLabel("EXIT_ACCEPTED", observed))
    }

    @Test
    fun marketExitKeepsMissingStagesVisibleAsMissing() {
        val observed = setOf("FILLED", "EXIT_CHECKED", "EXIT_SENT", "CLOSED")

        assertEquals("—", lifecycleAbsentStageLabel("EXIT_ACCEPTED", observed))
    }

    @Test
    fun expectedOrderIncludesExactExitFill() {
        assertTrue("EXIT_FILLED" in expectedOrderLifecycleStages)
    }
}

package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class PositionMetricsTest {
    @Test
    fun brokerStopTakesPriorityWhenInstalled() {
        assertEquals(28_000.0, effectiveStopLoss(28_000.0, 27_550.0), 0.000001)
    }

    @Test
    fun immutableHardStopKeepsRiskVisibleWhileBrokerStopIsMissing() {
        assertEquals(27_550.0, effectiveStopLoss(0.0, 27_550.0), 0.000001)
    }

    @Test
    fun missingStopDataRemainsUnavailable() {
        assertEquals(0.0, effectiveStopLoss(0.0, 0.0), 0.000001)
    }

    @Test
    fun pendingExecutorTargetKeepsRiskVisibleBeforeBrokerStopIsApplied() {
        assertEquals(27_187.5, effectiveStopLoss(0.0, 0.0, 27_187.5), 0.000001)
    }
}

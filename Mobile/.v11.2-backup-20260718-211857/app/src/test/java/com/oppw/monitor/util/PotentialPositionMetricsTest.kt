package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class PotentialPositionMetricsTest {
    @Test
    fun requiredDepositIsDividedByBalance() {
        assertEquals(0.075, potentialEffectiveLeverage(2_250.0, 30_000.0), 1e-12)
    }

    @Test
    fun fallbackIsUsedWhenBalanceIsUnavailable() {
        assertEquals(0.08, potentialEffectiveLeverage(2_250.0, 0.0, 0.08), 1e-12)
    }
}

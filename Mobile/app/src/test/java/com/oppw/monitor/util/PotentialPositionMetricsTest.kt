package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class PotentialPositionMetricsTest {
    @Test
    fun effectiveLeverageIncludesBrokerTwentyTimesMarginMultiplier() {
        assertEquals(1.5, potentialEffectiveLeverage(2_250.0, 30_000.0), 1e-12)
    }

    @Test
    fun userExampleProducesAboutTenPointThreeFourTimes() {
        assertEquals(10.3358673660, potentialEffectiveLeverage(2_170.0, 4_198.97), 1e-9)
    }

    @Test
    fun publisherFallbackIsUsedWhenBalanceIsUnavailable() {
        assertEquals(10.34, potentialEffectiveLeverage(2_250.0, 0.0, 10.34), 1e-12)
    }
}

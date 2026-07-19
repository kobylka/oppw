package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class PotentialPositionMetricsTest {
    @Test
    fun publisherCalculatedValueIsUsedWithoutAndroidRecalculation() {
        assertEquals(10.3358673660, potentialEffectiveLeverage(2_170.0, 4_198.97, 10.3358673660), 1e-9)
    }

    @Test
    fun missingPublisherValueDoesNotInventMargin() {
        assertEquals(0.0, potentialEffectiveLeverage(2_170.0, 4_198.97, 0.0), 1e-12)
    }
}

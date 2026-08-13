package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class FormattersTest {
    @Test
    fun volumePreservesBrokerSubCentilotPrecision() {
        assertEquals("0.002", volume(0.002))
        assertEquals("0.295", volume(0.295))
    }

    @Test
    fun volumeTrimsOnlyInsignificantTrailingZeroes() {
        assertEquals("0.3", volume(0.30))
        assertEquals("1", volume(1.0))
        assertEquals("0.00000001", volume(0.00000001))
    }
}

package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test
import java.util.TimeZone

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

    @Test
    fun executionTimestampUsesWarsawWhenDeviceIsUtc() {
        val original = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
            assertEquals("19 Aug 22:00:01.974", executionDateTime("2026-08-19T20:00:01.974Z"))
            assertEquals("20 Aug 00:01:06.069", executionDateTime("2026-08-19T22:01:06.069Z"))
        } finally {
            TimeZone.setDefault(original)
        }
    }

    @Test
    fun displayTimestampObservesWarsawDaylightSaving() {
        assertEquals("19 Jan 21:00:01", shortDateTime("2026-01-19T20:00:01Z"))
        assertEquals("19 Aug 22:00:01", shortDateTime("2026-08-19T20:00:01Z"))
    }
}

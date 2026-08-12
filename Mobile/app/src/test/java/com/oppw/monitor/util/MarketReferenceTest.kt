package com.oppw.monitor.util

import org.junit.Assert.assertEquals
import org.junit.Test

class MarketReferenceTest {
    @Test
    fun positionOpenOutranksWeekOpen() {
        val display = marketReferenceDisplay(29_797.5, 29_804.9)
        assertEquals("Position open", display.label)
        assertEquals(29_797.5, display.value!!, 0.000001)
    }

    @Test
    fun weekOpenRemainsWhenThereIsNoOpenPosition() {
        val display = marketReferenceDisplay(null, 29_804.9)
        assertEquals("Week open", display.label)
        assertEquals(29_804.9, display.value!!, 0.000001)
    }
}

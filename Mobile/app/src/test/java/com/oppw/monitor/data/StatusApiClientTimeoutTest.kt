package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Test

class StatusApiClientTimeoutTest {
    @Test
    fun analyticsUsesLongerReadTimeoutThanSmallApiResponses() {
        assertEquals(30_000, requestReadTimeoutMillis("analytics.php?account=DEMO&rolling_weeks=80"))
        assertEquals(8_000, requestReadTimeoutMillis("status.php?account=DEMO"))
    }
}

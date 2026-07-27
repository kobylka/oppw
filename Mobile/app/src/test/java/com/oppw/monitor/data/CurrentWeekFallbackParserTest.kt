package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class CurrentWeekFallbackParserTest {
    @Test
    fun usesLivePublisherWeekWhenBackendDerivedFieldsAreEmpty() {
        val response = JsonParser.parseResponse(
            """
            {
              "ok": true,
              "snapshot": {
                "connection": {"week": "2026-W31"},
                "account": {},
                "marketStats": {
                  "currentWeek": {
                    "week": "27 Jul - 02 Aug 2026",
                    "weekOpen": null,
                    "weeklyHigh": null,
                    "weeklyLow": null,
                    "weeklyClose": null
                  }
                },
                "market": {
                  "currentPrice": 28663.0,
                  "currentW1": {
                    "time": "2026-07-27T00:00:14.062000+02:00",
                    "open": 28676.0,
                    "high": 28762.25,
                    "low": 28499.53,
                    "close": 28663.0,
                    "source": "MT5_M1_WINDOW"
                  }
                }
              }
            }
            """.trimIndent(),
        )

        val week = assertNotNull(response.snapshot.marketStats.currentWeek).let {
            response.snapshot.marketStats.currentWeek!!
        }
        assertEquals(28676.0, week.weekOpen!!, 0.001)
        assertEquals(28762.25, week.weeklyHigh!!, 0.001)
        assertEquals(28499.53, week.weeklyLow!!, 0.001)
        assertEquals(28663.0, week.weeklyClose!!, 0.001)
        assertEquals("2026-07-27", week.weekOpenDate)
    }
}

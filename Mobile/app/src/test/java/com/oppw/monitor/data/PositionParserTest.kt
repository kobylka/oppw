package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class PositionParserTest {
    @Test
    fun parsesPendingSecondSessionBreakEvenAndImmutableHardStop() {
        val response = JsonParser.parseResponse(
            """
            {
              "ok": true,
              "generatedAt": "2026-07-20T10:00:00+02:00",
              "snapshot": {
                "connection": {},
                "account": {},
                "position": {
                  "ticket": 123,
                  "stopLoss": 0.0,
                  "breakEvenCheck": {
                    "status": "SCHEDULED_SIGNAL_PENDING",
                    "nextCheckAt": "2026-07-21T21:59:57+02:00"
                  },
                  "immutableHardStop": {
                    "price": 27550.0,
                    "lockedAt": "2026-07-20T09:45:00+02:00",
                    "source": "RECOVERY_INITIALIZATION"
                  },
                  "protectionTarget": {
                    "price": 27187.5,
                    "applied": false,
                    "reason": "SL",
                    "source": "PENDING_EXECUTOR_HARD_STOP",
                    "executorRequired": true
                  }
                }
              }
            }
            """.trimIndent(),
        )

        val position = assertNotNull(response.snapshot.position).let { response.snapshot.position!! }
        assertEquals("SCHEDULED_SIGNAL_PENDING", position.breakEvenCheck.status)
        assertEquals("2026-07-21T21:59:57+02:00", position.breakEvenCheck.nextCheckAt)
        assertEquals(27550.0, position.immutableHardStop.price, 0.000001)
        assertEquals("RECOVERY_INITIALIZATION", position.immutableHardStop.source)
        assertEquals(27187.5, position.protectionTarget.price, 0.000001)
        assertEquals(false, position.protectionTarget.applied)
        assertEquals(true, position.protectionTarget.executorRequired)
        assertEquals("PENDING_EXECUTOR_HARD_STOP", position.protectionTarget.source)
    }
}

package com.oppw.monitor

import com.oppw.monitor.data.JsonParser
import org.junit.Assert.assertEquals
import org.junit.Test

class JsonParserTest {
    @Test
    fun parsesSnapshotAndEvents() {
        val response = JsonParser.parseResponse(
            """{"ok":true,"generatedAt":"now","snapshot":{"connection":{"connected":true},"account":{},"position":null,"closestCondition":null,"equityHistory":[]},"events":[{"id":1,"name":"SYSTEM_START","message":"ok"}]}"""
        )
        assertEquals(true, response.snapshot.connection.connected)
        assertEquals("SYSTEM_START", response.events.single().name)
    }
}

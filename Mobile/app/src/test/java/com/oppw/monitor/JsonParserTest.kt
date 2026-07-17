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

    @Test
    fun parsesPairedSession() {
        val session = JsonParser.parseAuthSession(
            """{"ok":true,"session":{"accessToken":"a","accessTokenExpiresAt":"2026-07-17T10:15:00+00:00","refreshToken":"r","refreshTokenExpiresAt":"2026-10-15T10:00:00+00:00","device":{"id":"0123456789abcdef0123456789abcdef","name":"Samsung A53"},"allowedAccounts":[{"key":"REAL"},{"key":"DEMO"}]}}"""
        )
        assertEquals("Samsung A53", session.deviceName)
        assertEquals(listOf("REAL", "DEMO"), session.allowedAccountKeys)
    }
}

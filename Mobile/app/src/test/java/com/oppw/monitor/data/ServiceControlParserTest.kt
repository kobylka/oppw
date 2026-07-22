package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ServiceControlParserTest {
    @Test
    fun parsesMasterBackupAndRoleState() {
        val parsed = JsonParser.parseServiceControl(
            """{"ok":true,"generatedAt":"2026-07-22T12:00:00Z","accountKey":"REAL","canControl":true,"staleAfterSeconds":20,
                "master":{"configured":true,"online":true,"nodeId":"aaa","hostname":"master-pc","build":"oppw-52.0.0","lastSeenAt":"now"},
                "backup":{"configured":true,"online":true,"nodeId":"bbb","hostname":"backup-pc","build":"oppw-52.0.0","lastSeenAt":"now"},
                "roles":[{"role":"EXECUTOR","desiredRunning":true,"revision":3,"changedAt":"now","activeNodeRole":"MASTER",
                    "process":{"running":true,"pid":42,"startedAt":"now","restartCount":1,"lastExitCode":null},
                    "masterProcess":{"running":true,"pid":42},"backupProcess":{"running":false,"pid":0}}]}"""
        )
        assertTrue(parsed.canControl)
        assertTrue(parsed.master.online)
        assertEquals("master-pc", parsed.master.hostname)
        assertEquals("MASTER", parsed.roles.single().activeNodeRole)
        assertTrue(parsed.roles.single().process.running)
        assertFalse(parsed.roles.single().backupProcess.running)
        assertEquals(42L, parsed.roles.single().process.pid)
    }
}

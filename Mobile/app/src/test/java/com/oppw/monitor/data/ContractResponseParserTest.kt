package com.oppw.monitor.data

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

class ContractResponseParserTest {
    private fun response(name: String): String {
        val outputDirectory = System.getenv("OPPW_CONTRACT_OUTPUT_DIR").orEmpty()
        assumeTrue(
            "Actual backend responses are supplied by tools/validate_contracts.py",
            outputDirectory.isNotBlank(),
        )
        val file = File(outputDirectory, name)
        assertTrue("Missing contract response: ${file.absolutePath}", file.isFile)
        return file.readText()
    }

    @Test
    fun parsesActualBackendResponses() {
        val accounts = JsonParser.parseAccounts(response("accounts.json"))
        assertTrue(accounts.any { it.key == "DEMO" })

        val status = JsonParser.parseResponse(response("status.json"))
        val position = assertNotNull(status.snapshot.position).let { status.snapshot.position!! }
        assertEquals(990001L, position.ticket)
        assertEquals(0.02, position.volume, 0.000001)
        assertEquals(8000.0, status.snapshot.account.balance, 0.01)
        assertEquals(8125.5, status.snapshot.account.equity, 0.01)
        assertEquals(4393.0, status.snapshot.account.deposit, 0.01)
        assertTrue(status.snapshot.strategyDecision?.decisionId?.isNotBlank() == true)

        val analytics = JsonParser.parseAnalytics(response("analytics.json"))
        val quality = analytics.executionQuality
        assertEquals(1, quality.decisionToSend.sampleCount)
        assertEquals(100.0, quality.decisionToSend.medianMs!!, 0.01)
        assertEquals(150.0, quality.brokerAcknowledgement.medianMs!!, 0.01)
        assertEquals(300.0, quality.fill.medianMs!!, 0.01)
        assertEquals(300.0, quality.protectionAttachment.medianMs!!, 0.01)
        assertEquals(400.0, quality.backendPublication.medianMs!!, 0.01)
        assertEquals(1, quality.executorToMobile.sampleCount)
        assertTrue(
            quality.lifecycles.single().stages.map { it.stage }.containsAll(
                listOf("DECISION", "SENT", "ACCEPTED", "FILLED", "PROTECTED", "PUBLISHED"),
            ),
        )
    }
}

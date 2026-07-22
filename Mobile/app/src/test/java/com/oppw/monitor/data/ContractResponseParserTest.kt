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
        assertTrue(accounts.first { it.key == "DEMO" }.canControlService)

        val serviceControl = JsonParser.parseServiceControl(response("service-control.json"))
        assertTrue(serviceControl.canControl)
        assertTrue(serviceControl.master.online)
        assertEquals("MASTER", serviceControl.roles.first { it.role == "EXECUTOR" }.activeNodeRole)

        val status = JsonParser.parseResponse(response("status.json"))
        val position = assertNotNull(status.snapshot.position).let { status.snapshot.position!! }
        assertEquals(990001L, position.ticket)
        assertEquals(0.02, position.volume, 0.000001)
        assertEquals(8000.0, status.snapshot.account.balance, 0.01)
        assertEquals(8125.5, status.snapshot.account.equity, 0.01)
        assertEquals(4393.0, status.snapshot.account.deposit, 0.01)
        assertTrue(status.snapshot.strategyDecision?.decisionId?.isNotBlank() == true)
        assertEquals("BE CHECK", status.snapshot.closestCondition?.name)
        assertTrue(status.snapshot.conditions.any { it.name == "BE CHECK" })
        status.snapshot.marketStats.currentWeek!!.let { week ->
            assertEquals(110.0, week.dailyOpen!!, 0.01)
            assertEquals(112.0, week.dailyHigh!!, 0.01)
            assertEquals(108.0, week.dailyLow!!, 0.01)
            assertEquals(111.0, week.dailyClose!!, 0.01)
            assertEquals((112.0 / 110.0 - 1.0) * 100.0, week.dailyHighPercent!!, 0.01)
            assertEquals((108.0 / 110.0 - 1.0) * 100.0, week.dailyLowPercent!!, 0.01)
            assertEquals((111.0 / 110.0 - 1.0) * 100.0, week.dailyClosePercent!!, 0.01)
        }
        status.snapshot.marketStats.previousWeek!!.let { week ->
            assertEquals(220.0, week.dailyOpen!!, 0.01)
            assertEquals(224.0, week.dailyHigh!!, 0.01)
            assertEquals(216.0, week.dailyLow!!, 0.01)
            assertEquals(222.0, week.dailyClose!!, 0.01)
            assertEquals((224.0 / 220.0 - 1.0) * 100.0, week.dailyHighPercent!!, 0.01)
            assertEquals((216.0 / 220.0 - 1.0) * 100.0, week.dailyLowPercent!!, 0.01)
            assertEquals((222.0 / 220.0 - 1.0) * 100.0, week.dailyClosePercent!!, 0.01)
        }

        val analytics = JsonParser.parseAnalytics(response("analytics.json"))
        analytics.summary.let { summary ->
            assertEquals(0.1465, summary.averageWeeklyPreleverageReturnPercent, 0.01)
            assertEquals(1.15, summary.averageWeeklyLeveragedReturnPercent, 0.01)
            assertEquals(0.75, summary.averageWinPreleverageReturnPercent, 0.01)
            assertEquals(7.5, summary.averageWinLeveragedReturnPercent, 0.01)
            assertEquals(-0.6, summary.averageLossPreleverageReturnPercent, 0.01)
            assertEquals(-6.0, summary.averageLossLeveragedReturnPercent, 0.01)
            assertEquals(15.5568203721, summary.calmarRatio, 0.01)
            assertEquals(1.2014590348, summary.omegaRatio, 0.01)
            assertEquals(6.9714095393, summary.ulcerIndexPercent, 0.01)
            assertEquals(-10.0, summary.valueAtRisk95Percent, 0.01)
            assertEquals(-10.0, summary.expectedShortfall95Percent, 0.01)
            assertEquals(5, summary.riskSampleDays)
        }
        mapOf("A" to 1.0, "B" to 0.5, "C" to -0.2, "D" to -1.0).forEach { (tradeClass, expectedReturn) ->
            val value = analytics.tradeClasses.first { it.tradeClass == tradeClass }
            assertEquals(expectedReturn, value.averagePreleverageReturnPercent, 0.01)
        }
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

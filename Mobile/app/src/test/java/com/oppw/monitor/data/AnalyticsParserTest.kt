package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Test

class AnalyticsParserTest {
    @Test
    fun parsesReturnAndRiskMetricsWithPercentagePointUnits() {
        val analytics = JsonParser.parseAnalytics("""
            {
              "ok": true,
              "summary": {
                "averageWeeklyPreleverageReturnPercent": 0.1465,
                "averageWeeklyLeveragedReturnPercent": 1.15,
                "averageWinPreleverageReturnPercent": 0.75,
                "averageWinLeveragedReturnPercent": 7.5,
                "averageLossPreleverageReturnPercent": -0.6,
                "averageLossLeveragedReturnPercent": -6.0,
                "calmarRatio": 15.5568,
                "omegaRatio": 1.2015,
                "ulcerIndexPercent": 6.9714,
                "valueAtRisk95Percent": -10.0,
                "expectedShortfall95Percent": -10.0,
                "riskSampleDays": 5
              },
              "weekly": [{
                "week": "2026-W30",
                "preleverageReturnPercent": 0.798,
                "leveragedReturnPercent": 7.8
              }],
              "tradeClasses": [{
                "tradeClass": "A",
                "trades": 1,
                "averagePreleverageReturnPercent": 1.0
              }],
              "drawdown": {
                "sourceGranularity": "MINUTE",
                "cashFlowAdjusted": true,
                "statisticsExact": true,
                "sampleCount": 1440,
                "minuteSampleCount": 1440,
                "maxDrawdownPercent": 8.5,
                "maxDrawdownCurrency": 850.0,
                "averageDepthPercent": 4.25,
                "averageLengthSeconds": 3600,
                "longestLengthSeconds": 7200,
                "averageTroughRecoverySeconds": 1800,
                "timeUnderwaterPercent": 25.0,
                "ulcerIndexPercent": 2.75,
                "episodes": [{
                  "number": 1,
                  "startAt": "2026-07-27T10:00:00Z",
                  "troughAt": "2026-07-27T10:30:00Z",
                  "endAt": "2026-07-27T12:00:00Z",
                  "depthPercent": 8.5,
                  "recovered": true,
                  "elapsedSeconds": 7200,
                  "recoverySeconds": 5400,
                  "tradeKeys": ["DEMO:42"]
                }],
                "series": [{
                  "index": 1,
                  "capturedAt": "2026-07-27T10:00:00Z",
                  "equity": 10000,
                  "equityIndex": 100,
                  "drawdownPercent": 0,
                  "drawdownCurrency": 0,
                  "tradeKeys": ["DEMO:42"],
                  "sourceGranularity": "MINUTE"
                }]
              }
            }
        """.trimIndent())

        with(analytics.summary) {
            assertEquals(0.1465, averageWeeklyPreleverageReturnPercent, 0.000001)
            assertEquals(1.15, averageWeeklyLeveragedReturnPercent, 0.000001)
            assertEquals(0.75, averageWinPreleverageReturnPercent, 0.000001)
            assertEquals(7.5, averageWinLeveragedReturnPercent, 0.000001)
            assertEquals(-0.6, averageLossPreleverageReturnPercent, 0.000001)
            assertEquals(-6.0, averageLossLeveragedReturnPercent, 0.000001)
            assertEquals(15.5568, calmarRatio, 0.000001)
            assertEquals(1.2015, omegaRatio, 0.000001)
            assertEquals(6.9714, ulcerIndexPercent, 0.000001)
            assertEquals(-10.0, valueAtRisk95Percent, 0.000001)
            assertEquals(-10.0, expectedShortfall95Percent, 0.000001)
            assertEquals(5, riskSampleDays)
        }
        assertEquals(0.798, analytics.weekly.single().preleverageReturnPercent, 0.000001)
        assertEquals(7.8, analytics.weekly.single().leveragedReturnPercent, 0.000001)
        assertEquals(1.0, analytics.tradeClasses.single().averagePreleverageReturnPercent, 0.000001)
        with(analytics.drawdown) {
            assertEquals("MINUTE", sourceGranularity)
            assertEquals(true, cashFlowAdjusted)
            assertEquals(true, statisticsExact)
            assertEquals(1440, sampleCount)
            assertEquals(8.5, maxDrawdownPercent, 0.000001)
            assertEquals(850.0, maxDrawdownCurrency, 0.000001)
            assertEquals(7200L, longestLengthSeconds)
            assertEquals("2026-07-27T10:30:00Z", episodes.single().troughAt)
            assertEquals("2026-07-27T10:00:00Z", series.single().capturedAt)
            assertEquals(listOf("DEMO:42"), series.single().tradeKeys)
        }
    }

    @Test
    fun defaultsNewAdditiveMetricsForOlderAnalyticsPayloads() {
        val analytics = JsonParser.parseAnalytics("""
            {
              "ok": true,
              "summary": {},
              "drawdown": {
                "maxDrawdownPercent": 4.5,
                "averageMaePercent": -1.2,
                "series": [{
                  "index": 1,
                  "tradeKey": "DEMO:42",
                  "closedAt": "2026-07-27T10:00:00Z",
                  "equityIndex": 95.5,
                  "drawdownPercent": -4.5,
                  "maePercent": -1.2
                }]
              }
            }
        """.trimIndent())
        val summary = analytics.summary

        assertEquals(0.0, summary.averageWeeklyPreleverageReturnPercent, 0.0)
        assertEquals(0.0, summary.averageWeeklyLeveragedReturnPercent, 0.0)
        assertEquals(0.0, summary.averageWinPreleverageReturnPercent, 0.0)
        assertEquals(0.0, summary.averageLossLeveragedReturnPercent, 0.0)
        assertEquals(4.5, analytics.drawdown.maxDrawdownPercent, 0.0)
        assertEquals(0.0, analytics.drawdown.maxDrawdownCurrency, 0.0)
        assertEquals(0.0, analytics.drawdown.averageDepthPercent, 0.0)
        assertEquals(0.0, analytics.drawdown.series.single().equity, 0.0)
        assertEquals(0.0, analytics.drawdown.series.single().drawdownCurrency, 0.0)
    }
}

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
              }]
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
    }

    @Test
    fun defaultsNewAdditiveMetricsForOlderAnalyticsPayloads() {
        val summary = JsonParser.parseAnalytics("""{"ok":true,"summary":{}}""").summary

        assertEquals(0.0, summary.averageWeeklyPreleverageReturnPercent, 0.0)
        assertEquals(0.0, summary.averageWeeklyLeveragedReturnPercent, 0.0)
        assertEquals(0.0, summary.averageWinPreleverageReturnPercent, 0.0)
        assertEquals(0.0, summary.averageLossLeveragedReturnPercent, 0.0)
    }
}

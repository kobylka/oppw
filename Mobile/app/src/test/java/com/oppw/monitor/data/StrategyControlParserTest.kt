package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StrategyControlParserTest {
    @Test
    fun parsesFourPerAccountEntryRules() {
        val parsed = JsonParser.parseStrategyControl(
            """{"ok":true,"generatedAt":"2026-08-11T12:00:00Z","accountKey":"REAL","canControl":true,"revision":7,"changedAt":"now","rules":[
                {"key":"ARITHMETIC_LAST_TWO","label":"Last two weeks ≤ −2.00%","description":"Arithmetic rule","enabled":true},
                {"key":"GAP_MOMENTUM","label":"Gap ≥ 1.00% + momentum 20 ≤ −0.50%","description":"Combined rule","enabled":false},
                {"key":"TUESDAY_NORMALIZATION","label":"Tuesday within ±0.50% of Friday","description":"Tuesday rule","enabled":true},
                {"key":"PREMARKET_LOW","label":"Premarket range ≥ 0.80% + close in bottom 15%","description":"Combined premarket rule","enabled":true}
            ],"positionRevision":3,"positionChangedAt":"later","positionRules":[
                {"key":"OR5","scope":"OPEN_POSITION","label":"OR5 breakdown + 60-minute decline","description":"Exit rule","enabled":true}
            ]}"""
        )
        assertEquals("REAL", parsed.accountKey)
        assertTrue(parsed.canControl)
        assertEquals(7L, parsed.revision)
        assertEquals(4, parsed.rules.size)
        assertFalse(parsed.rules.first { it.key == "GAP_MOMENTUM" }.enabled)
        assertEquals("Tuesday within ±0.50% of Friday", parsed.rules.first { it.key == "TUESDAY_NORMALIZATION" }.label)
        assertEquals("Premarket range ≥ 0.80% + close in bottom 15%", parsed.rules.first { it.key == "PREMARKET_LOW" }.label)
        assertEquals(3L, parsed.positionRevision)
        assertEquals(1, parsed.positionRules.size)
        assertEquals("OPEN_POSITION", parsed.positionRules.single().scope)
        assertTrue(parsed.positionRules.single().enabled)
    }
}

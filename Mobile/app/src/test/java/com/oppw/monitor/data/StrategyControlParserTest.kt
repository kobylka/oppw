package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StrategyControlParserTest {
    @Test
    fun parsesFivePerAccountEntryRules() {
        val parsed = JsonParser.parseStrategyControl(
            """{"ok":true,"generatedAt":"2026-08-11T12:00:00Z","accountKey":"REAL","canControl":true,"revision":7,"changedAt":"now","rules":[
                {"key":"ARITHMETIC_LAST_TWO","label":"Last two weeks ≤ −2.00%","description":"Arithmetic rule","enabled":true},
                {"key":"GAP_MOMENTUM","label":"Gap ≥ 1.00% + momentum 20 ≤ −0.50%","description":"Combined rule","enabled":false},
                {"key":"TUESDAY_NORMALIZATION","label":"Tuesday within ±0.50% of Friday","description":"Tuesday rule","enabled":true},
                {"key":"PREMARKET_RANGE","label":"Premarket range ≥ 0.80%","description":"Range rule","enabled":true},
                {"key":"PREMARKET_CLOSE_NEAR_LOW","label":"Premarket close in bottom 15%","description":"Low rule","enabled":true}
            ]}"""
        )
        assertEquals("REAL", parsed.accountKey)
        assertTrue(parsed.canControl)
        assertEquals(7L, parsed.revision)
        assertEquals(5, parsed.rules.size)
        assertFalse(parsed.rules.first { it.key == "GAP_MOMENTUM" }.enabled)
        assertEquals("Tuesday within ±0.50% of Friday", parsed.rules.first { it.key == "TUESDAY_NORMALIZATION" }.label)
    }
}

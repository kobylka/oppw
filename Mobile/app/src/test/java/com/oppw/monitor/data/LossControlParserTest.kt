package com.oppw.monitor.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LossControlParserTest {
    @Test
    fun parsesEveryRuleStatusThresholdAndNullableLiveCondition() {
        val response = JsonParser.parseResponse(
            """
            {"ok":true,"snapshot":{"connection":{},"account":{},"potentialPosition":{
              "available":true,"lossControls":{"revision":7,"evaluatedAt":"2026-08-13T14:00:00+02:00",
              "currentPrice":22100.5,"currentPriceUsage":"preview","rules":[
                {"key":"ARITHMETIC_LAST_TWO","enabled":false,"applicable":true,"status":"DISABLED","effect":"SKIP_ENTRY","conditions":[
                  {"key":"ARITHMETIC_SUM","label":"Last two weekly outcomes sum","actual":-0.025,"operator":"<=","threshold":-0.02,"unit":"RATIO","met":true}]},
                {"key":"GAP_MOMENTUM","enabled":true,"applicable":true,"status":"WAITING","effect":"DEFER_OR_SKIP_ENTRY","conditions":[
                  {"key":"MOMENTUM_20","label":"Momentum","actual":null,"operator":"<=","threshold":-0.005,"unit":"RATIO","met":null}]}
              ]}}
            }}
            """.trimIndent(),
        )

        val controls = response.snapshot.potentialPosition!!.lossControls
        assertEquals(7, controls.revision)
        assertEquals(22100.5, controls.currentPrice, 0.000001)
        assertEquals(2, controls.rules.size)
        assertFalse(controls.rules[0].enabled)
        assertTrue(controls.rules[0].conditions.single().met!!)
        assertEquals(-0.02, controls.rules[0].conditions.single().threshold, 0.000001)
        assertNull(controls.rules[1].conditions.single().actual)
        assertNull(controls.rules[1].conditions.single().met)
    }

    @Test
    fun parsesOpenPositionOr5StatusSeparatelyFromEntryControls() {
        val response = JsonParser.parseResponse(
            """
            {"ok":true,"snapshot":{"connection":{},"account":{},"position":{
              "symbol":"US100","ticket":92,"openPrice":100.0,
              "lossControls":{"revision":3,"evaluatedAt":"2026-08-17T16:30:00+02:00",
              "currentPrice":98.5,"currentPriceUsage":"completed M1","rules":[
                {"key":"OR5","enabled":true,"applicable":true,"status":"MATCHED","effect":"EXIT_POSITION_MARKET_SELL","conditions":[
                  {"key":"OPENING_RANGE_BREAK","label":"Completed close vs OR5 low","actual":-0.01,"operator":"<=","threshold":0.0,"unit":"ratio","met":true}]}
              ]}}
            }}
            """.trimIndent(),
        )

        val controls = response.snapshot.position!!.lossControls
        assertEquals(3, controls.revision)
        assertEquals("OR5", controls.rules.single().key)
        assertEquals("MATCHED", controls.rules.single().status)
        assertTrue(controls.rules.single().conditions.single().met!!)
    }
}

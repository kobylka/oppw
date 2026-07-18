package com.oppw.monitor.util

import com.oppw.monitor.data.TradeAnalytics
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class TradeMetricsTest {
    @Test
    fun requiresFiveClosedTrades() {
        assertNull(closedTradeRatios(listOf(trade(10.0, 1000.0))).sharpe)
    }

    @Test
    fun ignoresOpenTradesAndCalculatesClosedTradeRatios() {
        val result = closedTradeRatios(listOf(
            trade(10.0, 1000.0), trade(-5.0, 1010.0), trade(20.0, 1005.0), trade(-10.0, 1025.0), trade(15.0, 1015.0), trade(999.0, 1.0, false),
        ))
        assertEquals(5, result.sampleSize)
        assertNotNull(result.sharpe)
        assertNotNull(result.sortino)
    }

    private fun trade(profit: Double, balanceBefore: Double, closed: Boolean = true) = TradeAnalytics(
        ticket = 1, symbol = "US100", side = "BUY", volume = 0.01, openedAt = "2026-01-01", closedAt = if (closed) "2026-01-02" else "",
        openPrice = 1.0, closePrice = 1.0, profit = profit, profitPercent = 0.0, balanceBefore = balanceBefore, tradeReturn = null,
        exitReason = "TO", durationSeconds = 1, mfePoints = 0.0, maePoints = 0.0, entrySlippagePoints = 0.0, exitSlippagePoints = 0.0,
        maxProfit = 0.0, maxDrawdown = 0.0, closed = closed,
    )
}

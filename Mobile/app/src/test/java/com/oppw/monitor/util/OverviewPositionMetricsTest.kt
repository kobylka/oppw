package com.oppw.monitor.util

import com.oppw.monitor.data.AccountStatus
import com.oppw.monitor.data.PositionStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class OverviewPositionMetricsTest {
    private val account = AccountStatus(
        currency = "PLN",
        strategyCapital = 8_000.0,
        deposit = 4_393.0,
        balance = 8_000.0,
        equity = 8_000.0,
    )

    @Test
    fun flatAccountShowsUnavailableForEveryPositionDependentMetric() {
        val display = overviewPositionDisplay(account, null)

        assertEquals(
            setOf("—"),
            setOf(
                display.deposit,
                display.currentProfit,
                display.currentProfitPercent,
                display.effectiveProfitPercent,
                display.strategyLeverage,
                display.leveragedProfitPercent,
                display.effectiveLeverage,
                display.exposure,
            ),
        )
    }

    @Test
    fun openPositionPreservesRealZeroValues() {
        val display = overviewPositionDisplay(account, openPosition())

        assertEquals("4,393.00 PLN", display.deposit)
        assertEquals("0.00 PLN", display.currentProfit)
        assertEquals("+0.00%", display.currentProfitPercent)
        assertEquals("+0.00%", display.effectiveProfitPercent)
        assertEquals("8x", display.strategyLeverage)
        assertEquals("+0.00%", display.leveragedProfitPercent)
        assertEquals("8.00x", display.effectiveLeverage)
        assertEquals("64,000.00 PLN", display.exposure)
    }

    private fun openPosition() = PositionStatus(
        symbol = "US100",
        side = "BUY",
        volume = 0.02,
        ticket = 1L,
        openedAt = "2026-07-27T15:29:57+02:00",
        openPrice = 32_000.0,
        bid = 32_000.0,
        ask = 32_001.0,
        priceTime = "2026-07-27T15:30:00+02:00",
        bidAt = "2026-07-27T15:30:00+02:00",
        askAt = "2026-07-27T15:30:00+02:00",
        tickAgeSeconds = 0.1,
        profit = 0.0,
        profitPercent = 0.0,
        strategyLeverage = 8.0,
        leveragedProfitPercent = 0.0,
        exposure = 64_000.0,
        effectiveLeverage = 8.0,
        stopLoss = 30_000.0,
        takeProfit = 0.0,
        potentialTakeProfit = 0.0,
        breakEvenArmed = false,
        protectionRegime = "HARD_SL",
        activeSlReason = "SL",
        activeTpReason = "",
    )
}

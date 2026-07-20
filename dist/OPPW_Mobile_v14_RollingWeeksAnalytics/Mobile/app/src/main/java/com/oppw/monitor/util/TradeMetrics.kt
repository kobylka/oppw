package com.oppw.monitor.util

import com.oppw.monitor.data.TradeAnalytics
import kotlin.math.sqrt

private const val MINIMUM_CLOSED_TRADES = 5

data class ClosedTradeRatios(val sharpe: Double?, val sortino: Double?, val sampleSize: Int)

fun closedTradeRatios(trades: List<TradeAnalytics>): ClosedTradeRatios {
    val returns = trades.asSequence()
        .filter { it.closed || it.closedAt.isNotBlank() }
        .mapNotNull(::closedTradeReturn)
        .filter { it.isFinite() }
        .toList()
    if (returns.size < MINIMUM_CLOSED_TRADES) return ClosedTradeRatios(null, null, returns.size)

    val mean = returns.average()
    val variance = returns.sumOf { value -> val difference = value - mean; difference * difference } / (returns.size - 1).toDouble()
    val standardDeviation = sqrt(variance)
    val downsideDeviation = sqrt(returns.sumOf { value -> val downside = value.coerceAtMost(0.0); downside * downside } / returns.size.toDouble())
    val sharpe = (mean / standardDeviation).takeIf { standardDeviation > 0.0 && it.isFinite() }
    val sortino = (mean / downsideDeviation).takeIf { downsideDeviation > 0.0 && it.isFinite() }
    return ClosedTradeRatios(sharpe, sortino, returns.size)
}

private fun closedTradeReturn(trade: TradeAnalytics): Double? {
    trade.tradeReturn?.takeIf { it.isFinite() }?.let { return it }
    if (trade.balanceBefore > 0.0 && trade.profit.isFinite()) return trade.profit / trade.balanceBefore
    return trade.profitPercent.takeIf { it.isFinite() }?.div(100.0)
}

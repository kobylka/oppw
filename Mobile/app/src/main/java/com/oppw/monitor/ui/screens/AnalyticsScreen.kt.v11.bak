package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.closedTradeRatios
import com.oppw.monitor.util.duration
import com.oppw.monitor.util.money
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.price
import com.oppw.monitor.util.shortDateTime

@Composable
fun AnalyticsScreen(state: UiState, onRetry: () -> Unit) {
    val analytics = state.analytics
    when {
        state.analyticsLoading && analytics == null -> LoadingPanel()
        analytics == null -> ErrorPanel(state.analyticsError ?: "No stored trade analytics yet", onRetry)
        else -> {
            val currency = state.response?.snapshot?.account?.currency ?: ""
            val s = analytics.summary
            val closedTradeRisk = closedTradeRatios(analytics.recentTrades)
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Performance", "${s.closedTrades} closed · ${s.openTrades} open")
                        MetricRow("Net profit", money(s.netProfit, currency), "Win rate", percent(s.winRate))
                        MetricRow("Profit factor", String.format("%.2f", s.profitFactor), "Expectancy", money(s.expectancy, currency))
                        MetricRow("Average win", money(s.averageWin, currency), "Average loss", money(s.averageLoss, currency))
                        MetricRow("Payoff ratio", String.format("%.2f", s.payoffRatio), "Recovery factor", String.format("%.2f", s.recoveryFactor))
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Capital-adjusted results")
                        MetricRow("Initial balance", money(s.initialBalance, currency), "Top-ups", money(s.topUps, currency))
                        MetricRow("Withdrawals", money(s.withdrawals, currency), "Net contributions", money(s.netContributions, currency))
                        MetricRow("Return on funded capital", percent(s.capitalAdjustedReturnPercent), "Positive weeks", percent(s.positiveWeeksPercent))
                        MetricRow("Average weekly P/L", money(s.averageWeeklyProfit, currency), "Total slippage", "${price(s.totalSlippagePoints)} pts")
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Trade quality")
                        MetricRow("Average MFE", "${price(s.averageMfePoints)} pts", "Average MAE", "${price(s.averageMaePoints)} pts")
                        MetricRow("Edge ratio", String.format("%.2f", s.edgeRatio), "Capture efficiency", percent(s.captureEfficiencyPercent))
                        MetricRow("Entry slippage", "${price(s.averageEntrySlippagePoints)} pts", "Exit slippage", "${price(s.averageExitSlippagePoints)} pts")
                        MetricRow("Median trade", money(s.medianProfit, currency), "Avg duration", duration(s.averageDurationSeconds.toLong()))
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Risk-adjusted performance", "${closedTradeRisk.sampleSize} closed-trade returns")
                        MetricRow("Trade Sharpe ratio", ratioText(closedTradeRisk.sharpe), "Trade Sortino ratio", ratioText(closedTradeRisk.sortino))
                        Text("Sharpe and Sortino use closed trades only and are not annualized.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        MetricRow("Calmar ratio", ratioText(s.calmarRatio), "Omega ratio", ratioText(s.omegaRatio))
                        MetricRow("Ulcer index", percentText(s.ulcerIndexPercent), "Daily VaR 95%", percentText(-s.valueAtRisk95Percent))
                        MetricRow("Expected shortfall 95%", percentText(-s.expectedShortfall95Percent), "Daily-risk sample", "${s.riskSampleDays} days")
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Risk and consistency")
                        MetricRow("Max drawdown", money(s.maxDrawdown, currency), "Time in market", percent(s.timeInMarketPercent))
                        MetricRow("Consistency score", String.format("%.2f", s.consistencyScore), "Best trade", money(s.bestTrade, currency))
                        MetricRow("Win streak", s.maxWinStreak.toString(), "Loss streak", s.maxLossStreak.toString())
                        MetricRow("Worst trade", money(s.worstTrade, currency), "Total trades", s.totalTrades.toString())
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Exit reasons", analytics.exitReasons.size.toString())
                        analytics.exitReasons.forEach { value ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(value.reason.ifBlank { "Unknown" }, style = MaterialTheme.typography.titleMedium)
                                Text("${value.trades} · ${percent(value.winRate)} · ${money(value.profit, currency)}", color = if (value.profit >= 0) BrightGreen else DangerRed)
                            }
                            Text("Avg ${money(value.averageProfit, currency)} · MFE ${price(value.averageMfePoints)} · MAE ${price(value.averageMaePoints)} pts", color = TextSecondary)
                        }
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Weekly summaries", analytics.weekly.size.toString())
                        analytics.weekly.take(16).forEach { week ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(week.week, style = MaterialTheme.typography.titleMedium)
                                Text(money(week.profit, currency), color = if (week.profit >= 0) BrightGreen else DangerRed)
                            }
                            Text("${week.trades} trades · ${percent(week.winRate)} wins · avg ${duration(week.averageDurationSeconds.toLong())}", color = TextSecondary)
                        }
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Recent trades", analytics.recentTrades.size.toString())
                        analytics.recentTrades.take(25).forEach { trade ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text("#${trade.ticket} · ${trade.exitReason.ifBlank { if (trade.closed) "Closed" else "OPEN" }}", style = MaterialTheme.typography.titleMedium)
                                Text(money(trade.profit, currency), color = if (trade.profit >= 0) BrightGreen else DangerRed)
                            }
                            Text("${shortDateTime(trade.openedAt)} · ${duration(trade.durationSeconds)} · MFE ${price(trade.mfePoints)} · MAE ${price(trade.maePoints)} pts", color = TextSecondary)
                            Text("Entry slip ${price(trade.entrySlippagePoints)} · Exit slip ${price(trade.exitSlippagePoints)} pts · Peak P/L ${money(trade.maxProfit, currency)} · Worst P/L ${money(trade.maxDrawdown, currency)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
                state.analyticsError?.let { item { ErrorPanel(it, onRetry) } }
            }
        }
    }
}

@Composable
private fun MetricRow(firstLabel: String, firstValue: String, secondLabel: String, secondValue: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Metric(firstLabel, firstValue, Modifier.weight(1f))
        Metric(secondLabel, secondValue, Modifier.weight(1f))
    }
}


private fun ratioText(value: Double?): String = value?.takeIf { it.isFinite() }?.let { String.format("%.2f", it) } ?: "N/A"
private fun percentText(value: Double?): String = value?.takeIf { it.isFinite() }?.let(::percent) ?: "N/A"

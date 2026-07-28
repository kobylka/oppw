package com.oppw.monitor.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.AnalyticsFilters
import com.oppw.monitor.data.AnalyticsResponse
import com.oppw.monitor.data.ExecutionLifecycle
import com.oppw.monitor.data.LatencySummary
import com.oppw.monitor.data.TradeAnalytics
import com.oppw.monitor.data.TradeDistribution
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.DrawdownEpisode
import com.oppw.monitor.util.drawdownStatistics
import com.oppw.monitor.util.duration
import com.oppw.monitor.util.executionDateTime
import com.oppw.monitor.util.money
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.price
import com.oppw.monitor.util.shortDateTime
import com.oppw.monitor.util.unsignedPercent
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

private data class DrillDown(val title: String, val tradeKeys: List<String>)

@Composable
fun AnalyticsScreen(state: UiState, onRetry: () -> Unit, onFiltersChanged: (AnalyticsFilters) -> Unit) {
    val analytics = state.analytics
    when {
        state.analyticsLoading && analytics == null -> LoadingPanel()
        analytics == null -> ErrorPanel(state.analyticsError ?: "No stored trade analytics yet", onRetry)
        else -> AnalyticsContent(state, analytics, onFiltersChanged)
    }
}

@Composable
private fun AnalyticsContent(state: UiState, analytics: AnalyticsResponse, onFiltersChanged: (AnalyticsFilters) -> Unit) {
    val currency = state.response?.snapshot?.account?.currency ?: ""
    val summary = analytics.summary
    val allTradeKeys = analytics.recentTrades.filter { it.closed }.map(::tradeKey)
    val distributionTradeKeys = analytics.tradeDistribution.trades.map { "${it.strategyKey}:${it.ticket}" }.distinct()
    val drawdowns = remember(analytics.drawdown) { drawdownStatistics(analytics.drawdown) }
    var drillDown by remember(analytics.generatedAt) { mutableStateOf<DrillDown?>(null) }
    var expandedExecutions by remember { mutableStateOf(setOf<String>()) }
    val openDrillDown: (String, List<String>) -> Unit = { title, keys -> drillDown = DrillDown(title, keys.distinct()) }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { FiltersPanel(state.analyticsFilters, analytics, onFiltersChanged) }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Filtered performance", "${summary.closedTrades} closed · ${summary.openTrades} open")
                MetricLink("Net profit", money(summary.netProfit, currency), sample(analytics, "netProfit", allTradeKeys), openDrillDown)
                MetricLink("Win rate", unsignedPercent(summary.winRate), sample(analytics, "winRate", allTradeKeys), openDrillDown)
                MetricLink("Profit factor", ratioValue(summary.profitFactor), sample(analytics, "profitFactor", allTradeKeys), openDrillDown)
                MetricLink("Expectancy", money(summary.expectancy, currency), sample(analytics, "expectancy", allTradeKeys), openDrillDown)
                MetricLink("Sharpe · annualized", ratioText(summary.sharpeRatio, summary.sharpeAvailable), sample(analytics, "sharpeRatio", allTradeKeys), openDrillDown)
                MetricLink("Sortino · annualized", if (summary.sortinoInfinite) "∞" else ratioText(summary.sortinoRatio, summary.sortinoAvailable), sample(analytics, "sortinoRatio", allTradeKeys), openDrillDown)
                Text("Each row opens the exact filtered trades used in the calculation. Ratios use closed-trade account returns and √${summary.periodsPerYear} annualization.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Trade distribution", "best → worst")
                Box(Modifier.fillMaxWidth().clickable(enabled = distributionTradeKeys.isNotEmpty()) { openDrillDown("Trade distribution", distributionTradeKeys) }) {
                    TradeDistributionChart(analytics.tradeDistribution, Modifier.fillMaxWidth().height(260.dp))
                }
                Text("Every closed trade is sorted by pre-leverage return. The left side is the best trade and the right side is the worst trade. Tap the chart to inspect the exact filtered trades.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Trade quality", "tap any metric for its exact sample")
                MetricLink("Gross profit", money(summary.grossProfit, currency), sample(analytics, "grossProfit", allTradeKeys), openDrillDown)
                MetricLink("Gross loss", money(summary.grossLoss, currency), sample(analytics, "grossLoss", allTradeKeys), openDrillDown)
                MetricLink("Median trade", money(summary.medianProfit, currency), sample(analytics, "medianProfit", allTradeKeys), openDrillDown)
                MetricLink("Average winner", money(summary.averageWin, currency), sample(analytics, "averageWin", allTradeKeys), openDrillDown)
                MetricLink("Average loser", money(summary.averageLoss, currency), sample(analytics, "averageLoss", allTradeKeys), openDrillDown)
                MetricLink("Payoff ratio", ratioValue(summary.payoffRatio), sample(analytics, "payoffRatio", allTradeKeys), openDrillDown)
                MetricLink("Best trade", money(summary.bestTrade, currency), sample(analytics, "bestTrade", allTradeKeys), openDrillDown)
                MetricLink("Worst trade", money(summary.worstTrade, currency), sample(analytics, "worstTrade", allTradeKeys), openDrillDown)
                MetricLink("Maximum win streak", summary.maxWinStreak.toString(), sample(analytics, "maxWinStreak", allTradeKeys), openDrillDown)
                MetricLink("Maximum loss streak", summary.maxLossStreak.toString(), sample(analytics, "maxLossStreak", allTradeKeys), openDrillDown)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Average returns", "filtered closed trades")
                MetricLink("Weekly P/L · pre-leverage", percent(summary.averageWeeklyPreleverageReturnPercent), sample(analytics, "averageWeeklyPreleverageReturn", allTradeKeys), openDrillDown)
                MetricLink("Weekly P/L · leveraged", percent(summary.averageWeeklyLeveragedReturnPercent), sample(analytics, "averageWeeklyLeveragedReturn", allTradeKeys), openDrillDown)
                MetricLink("All losses · pre-leverage", percent(summary.averageLossPreleverageReturnPercent), sample(analytics, "averageLossPreleverageReturn", allTradeKeys), openDrillDown)
                MetricLink("All losses · leveraged", percent(summary.averageLossLeveragedReturnPercent), sample(analytics, "averageLossLeveragedReturn", allTradeKeys), openDrillDown)
                MetricLink("All wins · pre-leverage", percent(summary.averageWinPreleverageReturnPercent), sample(analytics, "averageWinPreleverageReturn", allTradeKeys), openDrillDown)
                MetricLink("All wins · leveraged", percent(summary.averageWinLeveragedReturnPercent), sample(analytics, "averageWinLeveragedReturn", allTradeKeys), openDrillDown)
                Text("Weekly values compound closed trades inside each ISO week, then average the weekly results. Leveraged values are account returns: profit divided by balance before each trade.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Excursion, timing and execution", "closed trades")
                MetricLink("Average duration", duration(summary.averageDurationSeconds.toLong()), sample(analytics, "averageDuration", allTradeKeys), openDrillDown)
                MetricLink("Average MFE", "${price(summary.averageMfePoints)} pts", sample(analytics, "averageMfe", allTradeKeys), openDrillDown)
                MetricLink("Average MAE", "${price(summary.averageMaePoints)} pts", sample(analytics, "averageMae", allTradeKeys), openDrillDown)
                MetricLink("Entry slippage", "${price(summary.averageEntrySlippagePoints)} pts", sample(analytics, "entrySlippage", allTradeKeys), openDrillDown)
                MetricLink("Exit slippage", "${price(summary.averageExitSlippagePoints)} pts", sample(analytics, "exitSlippage", allTradeKeys), openDrillDown)
                MetricLink("Total slippage", "${price(summary.totalSlippagePoints)} pts", sample(analytics, "totalSlippage", allTradeKeys), openDrillDown)
                MetricLink("Capture efficiency", percent(summary.captureEfficiencyPercent), sample(analytics, "captureEfficiency", allTradeKeys), openDrillDown)
                MetricLink("Edge ratio", ratioValue(summary.edgeRatio), sample(analytics, "edgeRatio", allTradeKeys), openDrillDown)
                MetricLink("Time in market", unsignedPercent(summary.timeInMarketPercent), sample(analytics, "timeInMarket", allTradeKeys), openDrillDown)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Rolling 20-trade risk-adjusted ratios", "visible sample count")
                DualLineChart(
                    analytics.rolling20.map { it.sharpe to if (it.sortinoInfinite) null else it.sortino },
                    Modifier.fillMaxWidth().height(190.dp),
                )
                analytics.rolling20.takeLast(12).reversed().forEach { point ->
                    val sortino = if (point.sortinoInfinite) "∞" else nullableRatio(point.sortino)
                    MetricLink(
                        "${shortDateTime(point.closedAt)} · n=${point.sampleCount}",
                        "Sharpe ${nullableRatio(point.sharpe)} · Sortino $sortino",
                        point.tradeKeys,
                        openDrillDown,
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Confidence intervals", "95% · sample shown")
                analytics.confidenceIntervals.forEach { interval ->
                    MetricLink(
                        "${interval.label} · n=${interval.sampleCount}",
                        "${formatNumber(interval.estimate)}${interval.unit}  [${formatNumber(interval.lower95)}, ${formatNumber(interval.upper95)}]${interval.unit}",
                        interval.tradeKeys,
                        openDrillDown,
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("A/B/C/D profit contribution", "cumulative contribution")
                analytics.classProfitContribution.forEach { value ->
                    MetricLink(
                        "Class ${value.tradeClass} · ${value.trades} trades",
                        "P/L ${money(value.profit, currency)} · contribution ${percent(value.profitContributionPercent)} · cumulative ${money(value.cumulativeProfit, currency)}",
                        value.tradeKeys,
                        openDrillDown,
                        classColor(value.tradeClass),
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Average pre-leverage return by class", "filtered closed trades")
                analytics.classProfitContribution.forEach { value ->
                    MetricLink(
                        "Class ${value.tradeClass} · n=${value.trades}",
                        percent(value.averagePreleverageReturnPercent),
                        value.tradeKeys,
                        openDrillDown,
                        classColor(value.tradeClass),
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Class distribution", "year × leverage")
                analytics.classDistribution.sortedWith(compareByDescending<com.oppw.monitor.data.ClassDistributionPoint> { it.year }.thenBy { it.leverage }.thenBy { it.tradeClass }).forEach { value ->
                    MetricLink(
                        "${value.year} · ${formatLeverage(value.leverage)} · Class ${value.tradeClass}",
                        "${value.trades} trades · ${money(value.profit, currency)}",
                        value.tradeKeys,
                        openDrillDown,
                        classColor(value.tradeClass),
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Risk metrics", "${summary.riskSampleDays} returns · ${analytics.drawdown.sampleCount} samples")
                MetricLink("Calmar ratio · daily + minute low", ratioValue(summary.calmarRatio), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Omega ratio", ratioValue(summary.omegaRatio), emptyList(), openDrillDown)
                MetricLink("Ulcer index · daily + minute low", unsignedPercent(summary.ulcerIndexPercent), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Daily VaR 95% · loss", riskLossMagnitude(summary.valueAtRisk95Percent), emptyList(), openDrillDown)
                MetricLink("Expected shortfall 95% · loss", riskLossMagnitude(summary.expectedShortfall95Percent), emptyList(), openDrillDown)
                Text("Calmar and Ulcer use daily equity augmented with each day's lowest minute-equity point. VaR and expected shortfall remain daily-return metrics.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Daily-equity drawdown")
                DrawdownChart(analytics, Modifier.fillMaxWidth().height(190.dp))
                MetricLink("Maximum drawdown", percent(-abs(analytics.drawdown.maxDrawdownPercent)), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Maximum drawdown · currency", money(drawdownCurrencyValue(analytics.drawdown.maxDrawdownCurrency), currency), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Recovery factor", ratioValue(summary.recoveryFactor), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Average drawdown depth", percent(-drawdowns.averageDepthPercent), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Average drawdown length", duration(drawdowns.averageLengthSeconds.toLong()), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Longest drawdown length", duration(drawdowns.longestLengthSeconds), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Average trough-to-recovery length", duration(drawdowns.averageTroughRecoverySeconds.toLong()), analytics.drawdown.tradeKeys, openDrillDown)
                MetricLink("Time under water", unsignedPercent(drawdowns.timeUnderwaterPercent), analytics.drawdown.tradeKeys, openDrillDown)
                Text("Source: ${drawdownSourceLabel(analytics.drawdown.sourceGranularity)}. All aggregate values are cash-flow-adjusted and use each Warsaw weekday's first, lowest-minute, and closing equity points. This preserves intraday unrealized troughs without treating every minute fluctuation as a separate daily drawdown.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                Text("Episode cards below are formed only from closed-trade peaks and recoveries. Minute equity refines their starting point, lowest point, depth, recovery duration, and the current length of an ongoing episode. Account/scope and rolling-window filters apply to the equity curve; leverage, exit-reason, and class filters apply to the closed-trade list.", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item { SectionTitle("Closed-trade drawdowns", "${drawdowns.episodes.size}/${drawdowns.episodeCount} shown · ≥24h") }
        if (drawdowns.episodes.isEmpty()) {
            item { AppCard(Modifier.fillMaxWidth()) { Text("No closed-trade drawdown lasted at least 24 hours in the selected account window.", color = TextSecondary) } }
        } else {
            items(drawdowns.episodes.reversed(), key = { it.number }) { episode ->
                DrawdownEpisodeCard(episode, openDrillDown)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Before/after parameter changes", "strategy build or parameter hash")
                analytics.parameterComparison.forEach { build ->
                    MetricLink(
                        build.build.ifBlank { "Legacy" } + build.parameterHash.take(8).takeIf(String::isNotBlank)?.let { " · $it" }.orEmpty() + " · n=${build.trades}",
                        "${shortDateTime(build.firstClosedAt)} → ${shortDateTime(build.lastClosedAt)} · P/L ${money(build.netProfit, currency)} · mean ${percent(build.meanAccountReturnPercent)} · win ${unsignedPercent(build.winRate)} · Sharpe ${nullableRatio(build.sharpe)}",
                        build.tradeKeys,
                        openDrillDown,
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Strategy vs unleveraged US100", "same entry-to-exit windows")
                BenchmarkChart(analytics, Modifier.fillMaxWidth().height(190.dp))
                MetricLink("Strategy return · n=${analytics.benchmark.sampleCount}", percent(analytics.benchmark.strategyReturnPercent), analytics.benchmark.tradeKeys, openDrillDown)
                MetricLink("Unleveraged benchmark", percent(analytics.benchmark.benchmarkReturnPercent), analytics.benchmark.tradeKeys, openDrillDown)
                MetricLink("Excess return", percent(analytics.benchmark.excessReturnPercent), analytics.benchmark.tradeKeys, openDrillDown)
                Text(analytics.benchmark.label, color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            }
        }
        item {
            val quality = analytics.executionQuality
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Execution quality", "median / p95 latency")
                LatencyMetric("Decision → send", quality.decisionToSend, openDrillDown)
                LatencyMetric("Broker acknowledgement", quality.brokerAcknowledgement, openDrillDown)
                LatencyMetric("Fill", quality.fill, openDrillDown)
                LatencyMetric("Protection attachment", quality.protectionAttachment, openDrillDown)
                LatencyMetric("Backend publication", quality.backendPublication, openDrillDown)
                LatencyMetric("Executor → mobile", quality.executorToMobile, openDrillDown)
                MetricLink("Rejected requests", "${quality.rejections}/${quality.orderAttempts} attempts · ${unsignedPercent(quality.rejectionRatePercent)}", quality.rejectionTradeKeys, openDrillDown)
                MetricLink("Orders sent", "${quality.sentOrders}/${quality.orderAttempts} attempts", quality.sentTradeKeys, openDrillDown)
                MetricLink("Missed execution windows", quality.missedExecutionWindows.toString(), quality.missedWindowTradeKeys, openDrillDown)
                quality.fillingModes.forEach { (mode, count) -> MetricLink("Filling mode $mode", count.toString(), quality.fillingModeTradeKeys[mode].orEmpty(), openDrillDown) }
                quality.retcodes.forEach { (retcode, count) -> MetricLink("Retcode $retcode", count.toString(), quality.retcodeTradeKeys[retcode].orEmpty(), openDrillDown) }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Order lifecycle", analytics.executionQuality.lifecycles.size.toString())
                analytics.executionQuality.lifecycles.forEach { lifecycle ->
                    val expanded = lifecycle.executionId in expandedExecutions
                    LifecycleHeader(lifecycle, expanded) {
                        expandedExecutions = if (expanded) expandedExecutions - lifecycle.executionId else expandedExecutions + lifecycle.executionId
                    }
                    if (expanded) LifecycleStages(lifecycle)
                    HorizontalDivider(Modifier.padding(vertical = 5.dp))
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Exit reasons", analytics.exitReasons.size.toString())
                analytics.exitReasons.forEach { value ->
                    MetricLink(
                        value.reason.ifBlank { "Unknown" } + " · ${value.trades}",
                        "${unsignedPercent(value.winRate)} wins · ${money(value.profit, currency)} · MFE ${price(value.averageMfePoints)} · MAE ${price(value.averageMaePoints)} pts",
                        sample(analytics, "exit:${value.reason.ifBlank { "Unknown" }}", allTradeKeys),
                        openDrillDown,
                    )
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Recent filtered trades", analytics.recentTrades.size.toString())
                analytics.recentTrades.take(50).forEach { trade -> TradeRow(trade, currency) { openDrillDown("Trade ${trade.ticket}", listOf(tradeKey(trade))) } }
            }
        }
    }

    drillDown?.let { selection ->
        TradeDrillDownDialog(
            selection = selection,
            trades = analytics.recentTrades,
            currency = currency,
            onDismiss = { drillDown = null },
        )
    }
}

@Composable
private fun FiltersPanel(filters: AnalyticsFilters, analytics: AnalyticsResponse, onFiltersChanged: (AnalyticsFilters) -> Unit) {
    val options = analytics.filterOptions
    var rollingWeeksText by remember(filters.rollingWeeks) { mutableStateOf(filters.rollingWeeks.toString()) }
    val requestedRollingWeeks = rollingWeeksText.toIntOrNull()
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle("Analytics filters", "applied server-side")
        FilterMenu("Account scope", filters.scope, listOf("SELECTED", "ALL", "REAL", "DEMO")) { onFiltersChanged(filters.copy(scope = it)) }
        FilterMenu("Leverage", filters.leverage.ifBlank { "All" }, listOf("") + options.leverages.map(::formatLeverage)) { onFiltersChanged(filters.copy(leverage = it.removeSuffix("x").takeUnless { value -> value == "All" }.orEmpty())) }
        FilterMenu("Exit reason", filters.exitReason.ifBlank { "All" }, listOf("") + options.exitReasons) { onFiltersChanged(filters.copy(exitReason = it.takeUnless { value -> value == "All" }.orEmpty())) }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = rollingWeeksText,
                onValueChange = { value -> if (value.length <= 3 && value.all(Char::isDigit)) rollingWeeksText = value },
                modifier = Modifier.fillMaxWidth(0.55f),
                label = { Text("Rolling weeks") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            )
            OutlinedButton(
                enabled = requestedRollingWeeks != null && requestedRollingWeeks in 1..520 && requestedRollingWeeks != filters.rollingWeeks,
                onClick = { requestedRollingWeeks?.let { onFiltersChanged(filters.copy(rollingWeeks = it)) } },
            ) { Text("Apply") }
        }
        Text(
            if (options.availableWeeks > 0) "Using ${options.effectiveRollingWeeks} of ${options.availableWeeks} available calendar weeks"
            else "No weekly trade data available",
            color = TextSecondary,
            style = MaterialTheme.typography.labelMedium,
        )
        FilterMenu("Class", filters.tradeClass.ifBlank { "All" }, listOf("") + options.classes) { onFiltersChanged(filters.copy(tradeClass = it.takeUnless { value -> value == "All" }.orEmpty())) }
        TextButton(onClick = { onFiltersChanged(AnalyticsFilters()) }) { Text("Reset filters") }
    }
}

@Composable
private fun FilterMenu(label: String, selected: String, values: List<String>, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = TextSecondary)
        Box {
            OutlinedButton(onClick = { expanded = true }) { Text(selected.ifBlank { "All" }) }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                values.distinct().forEach { raw ->
                    val display = raw.ifBlank { "All" }
                    DropdownMenuItem(text = { Text(display) }, onClick = { expanded = false; onSelect(display) })
                }
            }
        }
    }
}

@Composable
private fun MetricLink(label: String, value: String, tradeKeys: List<String>, onClick: (String, List<String>) -> Unit, valueColor: Color = MaterialTheme.colorScheme.onSurface) {
    Row(
        Modifier.fillMaxWidth().clickable(enabled = tradeKeys.isNotEmpty()) { onClick(label, tradeKeys) }.padding(vertical = 7.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = TextSecondary, modifier = Modifier.fillMaxWidth(0.54f))
        Text(value, color = valueColor, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun DrawdownEpisodeCard(episode: DrawdownEpisode, onClick: (String, List<String>) -> Unit) {
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle("Drawdown #${episode.number}", if (episode.recovered) "RECOVERED" else "ONGOING")
        Text(
            "${shortDateTime(episode.startAt)} to ${if (episode.recovered) shortDateTime(episode.endAt) else "latest sample"}",
            color = TextSecondary,
            style = MaterialTheme.typography.labelMedium,
        )
        MetricLink("Depth", percent(-episode.depthPercent), episode.tradeKeys, onClick, DangerRed)
        MetricLink("Length", duration(episode.elapsedSeconds), episode.tradeKeys, onClick)
        MetricLink(
            if (episode.troughSource == "MINUTE_EQUITY") "Trough · minute equity" else "Trough",
            shortDateTime(episode.troughAt),
            episode.tradeKeys,
            onClick,
        )
        MetricLink(
            "Trough-to-recovery",
            episode.recoverySeconds?.let(::duration) ?: "Ongoing",
            episode.tradeKeys,
            onClick,
            if (episode.recovered) BrightGreen else DangerRed,
        )
    }
}

private fun drawdownSourceLabel(source: String): String = when (source) {
    "DAILY_CLOSE_WITH_MINUTE_LOW" -> "daily + minute low"
    "DAILY_CLOSE_WITH_MINUTE_LOW_AND_DAILY_FALLBACK" -> "daily + minute low + retained history"
    "MINUTE" -> "minute samples"
    "MINUTE_WITH_DAILY_FALLBACK" -> "minute + retained daily history"
    "DAILY_FALLBACK" -> "retained daily history"
    "NONE" -> "no equity samples"
    else -> "legacy backend series"
}

@Composable
private fun LatencyMetric(label: String, value: LatencySummary, onClick: (String, List<String>) -> Unit) {
    val display = if (value.sampleCount == 0) "N/A · n=0" else "${milliseconds(value.medianMs)} / ${milliseconds(value.p95Ms)} · n=${value.sampleCount}"
    MetricLink(label, display, value.tradeKeys, onClick)
}

@Composable
private fun LifecycleHeader(lifecycle: ExecutionLifecycle, expanded: Boolean, onToggle: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(vertical = 7.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Column {
            Text("${lifecycle.strategyKey} · ${lifecycle.executionId.take(8)}", fontWeight = FontWeight.Medium)
            Text("Decision ${lifecycle.decisionId.take(8).ifBlank { "—" }} · ticket ${lifecycle.positionTicket.takeIf { it > 0 } ?: 0}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
        }
        Text(if (expanded) "Hide" else "Expand", color = PrimaryBlue)
    }
}

@Composable
private fun LifecycleStages(lifecycle: ExecutionLifecycle) {
    val expected = listOf("SIGNAL", "DECISION", "CHECKED", "SENT", "ACCEPTED", "FILLED", "POSITION_VISIBLE", "PROTECTED", "MODIFIED", "EXIT_CHECKED", "EXIT_SENT", "EXIT_ACCEPTED", "CLOSED", "PUBLISHED", "MOBILE_RECEIPT")
    val stages = lifecycle.stages.groupBy { it.stage }.mapValues { (stage, values) ->
        if (stage == "MODIFIED") values.last() else values.firstOrNull { it.result != false } ?: values.last()
    }
    expected.forEach { name ->
        val stage = stages[name]
        Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(if (stage == null) "○ $name" else if (stage.result == false) "× $name" else "● $name", color = when { stage == null -> TextSecondary; stage.result == false -> DangerRed; else -> BrightGreen })
            Text(stage?.let { executionDateTime(it.eventAt) } ?: "—", color = TextSecondary)
        }
        if (stage != null && (stage.retcode.isNotBlank() || stage.fillingMode.isNotBlank() || stage.reason.isNotBlank())) {
            Text(listOfNotNull(stage.retcode.takeIf(String::isNotBlank)?.let { "retcode $it" }, stage.fillingMode.takeIf(String::isNotBlank), stage.reason.takeIf(String::isNotBlank)).joinToString(" · "), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun TradeRow(trade: TradeAnalytics, currency: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 7.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Column {
            Text("${trade.strategyKey} #${trade.ticket} · Class ${trade.tradeClass.ifBlank { "?" }} · ${formatLeverage(trade.entryLeverage)}", fontWeight = FontWeight.Medium)
            Text("${shortDateTime(trade.closedAt.ifBlank { trade.openedAt })} · ${trade.exitReason.ifBlank { "Open" }}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(money(trade.profit, currency), color = if (trade.profit >= 0) BrightGreen else DangerRed)
            Text(percent(trade.preleverageReturnPercent), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun TradeDrillDownDialog(selection: DrillDown, trades: List<TradeAnalytics>, currency: String, onDismiss: () -> Unit) {
    val keySet = selection.tradeKeys.toSet()
    val selected = trades.filter { tradeKey(it) in keySet }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(selection.title) },
        text = {
            Column {
                Text("${selection.tradeKeys.size} trade keys · ${selected.size} records returned", color = TextSecondary)
                LazyColumn(Modifier.heightIn(max = 460.dp)) {
                    items(selected, key = { tradeKey(it) }) { trade -> TradeRow(trade, currency) {} }
                    if (selected.isEmpty()) item { Text("No matching trade record was returned for this metric. Execution-only samples can be inspected in the lifecycle panel.", color = TextSecondary) }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
    )
}

@Composable
private fun DualLineChart(values: List<Pair<Double?, Double?>>, modifier: Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val secondary = MaterialTheme.colorScheme.tertiary
    Canvas(modifier) {
        val points = values.flatMap { listOfNotNull(it.first, it.second) }
        if (values.size < 2 || points.isEmpty()) return@Canvas
        val low = min(0.0, points.minOrNull() ?: 0.0)
        val high = max(0.0, points.maxOrNull() ?: 0.0)
        val range = (high - low).takeIf { it > 1e-9 } ?: 1.0
        fun line(selector: (Pair<Double?, Double?>) -> Double?, color: Color) {
            val path = Path(); var started = false
            values.forEachIndexed { index, value -> selector(value)?.let { yValue ->
                val x = index.toFloat() / (values.size - 1).coerceAtLeast(1) * size.width
                val y = size.height - ((yValue - low) / range).toFloat() * size.height
                if (!started) { path.moveTo(x, y); started = true } else path.lineTo(x, y)
            } }
            if (started) drawPath(path, color, style = Stroke(width = 3f, cap = StrokeCap.Round))
        }
        val zeroY = size.height - ((0.0 - low) / range).toFloat() * size.height
        drawLine(Color.Gray.copy(alpha = 0.35f), Offset(0f, zeroY), Offset(size.width, zeroY), 1f)
        line({ it.first }, primary); line({ it.second }, secondary)
    }
}

@Composable
private fun DrawdownChart(analytics: AnalyticsResponse, modifier: Modifier) {
    val color = DangerRed
    val series = analytics.drawdown.series
    Canvas(modifier) {
        if (series.size < 2) return@Canvas
        val low = min(-0.01, series.minOf { it.drawdownPercent })
        val path = Path()
        series.forEachIndexed { index, point ->
            val x = index.toFloat() / (series.size - 1) * size.width
            val y = (point.drawdownPercent / low).toFloat().coerceIn(0f, 1f) * size.height
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color, style = Stroke(width = 3f, cap = StrokeCap.Round))
    }
}

@Composable
private fun BenchmarkChart(analytics: AnalyticsResponse, modifier: Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val secondary = MaterialTheme.colorScheme.tertiary
    val series = analytics.benchmark.series
    Canvas(modifier) {
        if (series.size < 2) return@Canvas
        val values = series.flatMap { listOf(it.strategyIndex, it.benchmarkIndex) }
        val low = values.minOrNull() ?: 0.0; val high = values.maxOrNull() ?: 1.0; val range = (high - low).takeIf { it > 1e-9 } ?: 1.0
        fun drawSeries(selector: (com.oppw.monitor.data.BenchmarkPoint) -> Double, color: Color) {
            val path = Path()
            series.forEachIndexed { index, point ->
                val x = index.toFloat() / (series.size - 1) * size.width
                val y = size.height - ((selector(point) - low) / range).toFloat() * size.height
                if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            drawPath(path, color, style = Stroke(width = 3f, cap = StrokeCap.Round))
        }
        drawSeries({ it.strategyIndex }, primary); drawSeries({ it.benchmarkIndex }, secondary)
    }
}

@Composable
private fun TradeDistributionChart(distribution: TradeDistribution, modifier: Modifier = Modifier) {
    val trades = distribution.trades.sortedByDescending { it.returnPercent }
    if (trades.isEmpty()) {
        Box(modifier.background(MaterialTheme.colorScheme.surfaceVariant), contentAlignment = Alignment.Center) {
            Text("No closed trades", color = TextSecondary)
        }
        return
    }

    val values = trades.map { it.returnPercent }
    val minValue = min(values.minOrNull() ?: 0.0, distribution.meanReturnPercent)
    val maxValue = max(values.maxOrNull() ?: 0.0, distribution.meanReturnPercent)
    val span = max(0.0001, maxValue - minValue)

    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().weight(1f)) {
            val left = 10.dp.toPx()
            val right = size.width - 10.dp.toPx()
            val top = 12.dp.toPx()
            val bottom = size.height - 20.dp.toPx()
            fun x(index: Int): Float = if (trades.size == 1) (left + right) / 2f else left + (right - left) * index.toFloat() / (trades.size - 1).toFloat()
            fun y(value: Double): Float = bottom - ((value - minValue) / span).toFloat() * (bottom - top)

            val zeroY = y(0.0)
            if (zeroY in top..bottom) drawLine(Color.Gray.copy(alpha = 0.55f), Offset(left, zeroY), Offset(right, zeroY), 1.dp.toPx())

            val meanY = y(distribution.meanReturnPercent)
            drawLine(Color(0xFFE53935), Offset(left, meanY), Offset(right, meanY), 1.5.dp.toPx())

            val path = Path()
            trades.forEachIndexed { index, trade ->
                val point = Offset(x(index), y(trade.returnPercent))
                if (index == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
            }
            drawPath(path, Color(0xFF3DDC84), style = Stroke(2.dp.toPx(), cap = StrokeCap.Round))

            trades.forEachIndexed { index, trade ->
                drawCircle(classColorRaw(trade.tradeClass), 3.dp.toPx(), Offset(x(index), y(trade.returnPercent)))
            }
        }

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Best ${String.format("%.2f%%", values.first())}", color = BrightGreen, style = MaterialTheme.typography.labelSmall)
            Text("Mean ${String.format("%.2f%%", distribution.meanReturnPercent)}", color = Color(0xFFE53935), style = MaterialTheme.typography.labelSmall)
            Text("Worst ${String.format("%.2f%%", values.last())}", color = DangerRed, style = MaterialTheme.typography.labelSmall)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            listOf("A", "B", "C", "D").forEach { value ->
                Text("● $value", color = classColor(value), style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

private fun sample(analytics: AnalyticsResponse, key: String, fallback: List<String>): List<String> = analytics.metricSamples[key].orEmpty().ifEmpty { fallback }
private fun tradeKey(trade: TradeAnalytics): String = "${trade.strategyKey}:${trade.ticket}"
private fun ratioText(value: Double, available: Boolean): String = if (available && value.isFinite()) String.format("%.2f", value) else "N/A"
private fun nullableRatio(value: Double?): String = if (value != null && value.isFinite()) String.format("%.2f", value) else "N/A"
private fun ratioValue(value: Double): String = if (value.isFinite()) String.format("%.2f", value) else "∞"
private fun riskLossMagnitude(value: Double): String = unsignedPercent(max(0.0, -value))
private fun drawdownCurrencyValue(value: Double): Double = if (value.isFinite() && value != 0.0) -abs(value) else 0.0
private fun formatNumber(value: Double): String = String.format("%.2f", value)
private fun milliseconds(value: Double?): String = when {
    value == null || !value.isFinite() -> "N/A"
    value >= 1000.0 -> String.format("%.2fs", value / 1000.0)
    value >= 100.0 -> String.format("%.0fms", value)
    value >= 10.0 -> String.format("%.1fms", value)
    else -> String.format("%.2fms", value)
}
private fun formatLeverage(value: Double): String = if (value <= 0) "—" else if (value % 1.0 == 0.0) "${value.toInt()}x" else String.format("%.2fx", value)
private fun classColor(value: String): Color = classColorRaw(value)
private fun classColorRaw(value: String): Color = when (value.uppercase()) {
    "A" -> Color(0xFF00C853)
    "B" -> Color(0xFF64B5F6)
    "C" -> Color(0xFFFFB300)
    else -> Color(0xFFEF5350)
}

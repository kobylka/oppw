package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.PriceCondition
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.RiskBar
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.components.StatusChip
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.age
import com.oppw.monitor.util.humanProtection
import com.oppw.monitor.util.leverage
import com.oppw.monitor.util.liveSourceAge
import com.oppw.monitor.util.money
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.unsignedPercent
import com.oppw.monitor.util.price
import com.oppw.monitor.util.shortDateTime
import com.oppw.monitor.util.timeOnly
import com.oppw.monitor.util.volume
import kotlin.math.abs

@Composable
fun PositionScreen(state: UiState, onRetry: () -> Unit) {
    when {
        state.loading && state.response == null -> LoadingPanel()
        state.response == null -> ErrorPanel(state.error ?: "No data", onRetry)
        else -> {
            val snapshot = state.response!!.snapshot
            val position = snapshot.position
            if (position == null) {
                val account = snapshot.account
                val potential = snapshot.potentialPosition
                val decision = snapshot.strategyDecision
                LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Column {
                                    Text("No open position", style = MaterialTheme.typography.titleLarge)
                                    Text("Waiting for the next strategy entry.", color = TextSecondary)
                                }
                                StatusChip("FLAT")
                            }
                        }
                    }
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Pre-trade what-if ticket", if (potential?.available == true) "LIVE MT5" else "UNAVAILABLE")
                            when {
                                potential == null -> Text("The publisher has not supplied the v43 potentialPosition object.", color = TextSecondary)
                                !potential.available -> {
                                    Text("MT5 could not calculate the next trade.", color = TextSecondary)
                                    if (potential.error.isNotBlank()) Text(potential.error, color = DangerRed)
                                    Metric("Chosen strategy leverage", leverage(potential.strategyLeverage))
                                    if (potential.leverageReason.isNotBlank()) Text(potential.leverageReason)
                                }
                                else -> {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Column {
                                            Text("${potential.side} ${potential.symbol}", style = MaterialTheme.typography.headlineMedium)
                                            Text("Calculated at current MT5 BUY price", color = TextSecondary)
                                        }
                                        StatusChip("${potential.strategyLeverage.toInt()}x", "green")
                                    }
                                    val effectiveLeverage = if (potential.balance > 0.0 && potential.requiredDeposit > 0.0) 20.0 * potential.requiredDeposit / potential.balance else potential.effectiveLeverage
                                    MetricRow("Potential volume", volume(potential.volume), "Current price", price(potential.price), BrightGreen)
                                    MetricRow("Required deposit", money(potential.requiredDeposit, account.currency), "Effective leverage", leverage(effectiveLeverage))
                                    MetricRow("Balance", money(potential.balance, account.currency), "Equity", money(potential.equity, account.currency))
                                    MetricRow("Free margin now", money(potential.freeMargin, account.currency), "Free margin after", money(potential.freeMarginAfter, account.currency), if (potential.freeMarginAfter >= 0.0) BrightGreen else DangerRed)
                                    MetricRow("Margin usage", unsignedPercent(potential.marginUsagePercent), "Margin level after", unsignedPercent(potential.marginLevelAfterPercent))
                                    MetricRow("Potential notional", money(potential.positionNotional, account.currency), "Sizing units", potential.sizingUnits.toString())
                                    Text("Margin source: ${potential.depositSource}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                    }
                    if (potential?.available == true) {
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("Potential hard stop loss", if (potential.accountLossCapApplied) "50% ACCOUNT CAP" else "")
                                MetricRow("Stop price", price(potential.potentialStopLossPrice), "Cash P/L at stop", money(potential.potentialStopLossCash, account.currency), DangerRed)
                                MetricRow("Account return at stop", percent(potential.accountLossPercentAtStop), "Risk cap", if (potential.accountLossCapApplied) "APPLIED" else "NOT REQUIRED", DangerRed)
                                if (potential.accountLossCapApplied) Text("The stop was moved closer so the projected account loss does not exceed 50% of balance.", color = TextSecondary)
                            }
                        }
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("What-if scenarios", potential.scenarios.size.toString())
                                potential.scenarios.forEach { scenario ->
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(scenario.label, style = MaterialTheme.typography.titleMedium)
                                        Text(money(scenario.profit, account.currency), color = if (scenario.profit >= 0.0) BrightGreen else DangerRed)
                                    }
                                    Text("Price ${price(scenario.price)} · underlying ${percent(scenario.underlyingReturnPercent)} · account ${percent(scenario.accountReturnPercent)} · balance ${money(scenario.balanceAfter, account.currency)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                    }
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Strategy decision recorder", decision?.outcome ?: "NO RECORD")
                            if (decision == null) {
                                Text("No structured strategy decision has been published yet.", color = TextSecondary)
                            } else {
                                val labeledTrade = snapshot.lastClosedTrade
                                val useLabeledTrade = abs(decision.previousTradeChange) <= 1e-12 && labeledTrade != null && abs(labeledTrade.preleverageReturn) > 1e-12
                                val previousTradeChange = if (useLabeledTrade) labeledTrade!!.preleverageReturn else decision.previousTradeChange
                                val previousTradeSource = if (useLabeledTrade) "publisher-labeled last trade" else decision.previousTradeSource
                                MetricRow("Selected leverage", leverage(decision.selectedLeverage), "Decision ID", decision.decisionId.take(8))
                                MetricRow("Previous full week", percent(decision.previousFullWeekChange * 100.0), "Previous trade", percent(previousTradeChange * 100.0))
                                Text(decision.leverageReason, style = MaterialTheme.typography.bodyLarge)
                                Text("Week source: ${decision.previousFullWeekSource}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                Text("Trade source: $previousTradeSource", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                Text("Recorded ${shortDateTime(decision.recordedAt)} · build ${decision.build}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                if (decision.error.isNotBlank()) Text(decision.error, color = DangerRed)
                            }
                        }
                    }
                    snapshot.lastClosedTrade?.let { trade ->
                        item {
                            AppCard(Modifier.fillMaxWidth()) {
                                SectionTitle("Last publisher-labeled trade", "Class ${trade.tradeClass}")
                                MetricRow("Pre-leverage return", percent(trade.preleverageReturnPercent), "Exit reason", trade.exitReason)
                                Text("Closed ${shortDateTime(trade.closedAt)} · position ${trade.positionIdentifier}", color = TextSecondary)
                            }
                        }
                    }
                    state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
                }
                return
            }

            val account = snapshot.account
            val ohPending = snapshot.connection.nextAction.equals("OH", true)
            val visibleConditions = snapshot.conditions.filterNot { it.name.equals("OH", true) && !ohPending }.sortedBy { it.distancePoints }
            val rawClosest = snapshot.closestCondition?.takeUnless { it.name.equals("OH", true) && !ohPending } ?: visibleConditions.firstOrNull()
            val conditions = visibleConditions.filterNot { sameCondition(it, rawClosest) }
            val closest = rawClosest
            val minimumBalance = account.deposit * 1.765
            val exposure = position.exposure.takeIf { it > 0.0 } ?: account.deposit * 20.0
            val effectiveLeverage = position.effectiveLeverage.takeIf { it > 0.0 } ?: if (account.balance > 0.0) exposure / account.balance else 0.0
            val potentialTakeProfit = position.potentialTakeProfit.takeIf { it > 0.0 } ?: visibleConditions.firstOrNull { it.name.equals("OH", true) || it.name.equals("CH", true) }?.targetPrice ?: 0.0
            val liveTickAge = liveSourceAge(position.tickAgeSeconds, position.priceTime.ifBlank { snapshot.connection.lastSync }, state.nowEpochMs)
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Column {
                                Text(position.symbol, style = MaterialTheme.typography.headlineMedium)
                                Text("Ticket ${position.ticket}", color = TextSecondary)
                                Text("Opened ${shortDateTime(position.openedAt)}", color = TextSecondary)
                            }
                            StatusChip(position.side, "green")
                        }
                        MetricRow("Volume", volume(position.volume), "Open price", price(position.openPrice))
                        MetricRow("Current bid", price(position.bid), "Current ask", price(position.ask), if (position.profit >= 0) BrightGreen else DangerRed)
                        MetricRow("Bid time", timeOnly(position.bidAt.ifBlank { position.priceTime }), "Ask time", timeOnly(position.askAt.ifBlank { position.priceTime }))
                        Text("Price age: ${age(liveTickAge)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        MetricRow("Stop loss", price(position.stopLoss), "Potential OH/CH target", price(potentialTakeProfit), DangerRed)
                    }
                }
                item { ConditionCard("Closest condition", closest, true) }
                item { SectionTitle("All other conditions", conditions.size.toString()) }
                if (conditions.isEmpty()) item { AppCard(Modifier.fillMaxWidth()) { Text("No other active price conditions.", color = TextSecondary) } }
                else items(conditions.size, key = { index -> "condition-${conditions[index].name}-$index" }) { index -> ConditionCard(conditions[index].name, conditions[index], false) }
                item { AppCard(Modifier.fillMaxWidth()) { SectionTitle("Risk to stop loss"); RiskBar(position.stopLoss, position.openPrice, position.bid) } }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        MetricRow("Unrealized P/L", money(position.profit, account.currency), "P/L % leveraged", percent(position.leveragedProfitPercent), if (position.profit >= 0) BrightGreen else DangerRed)
                        MetricRow("Exposure", money(exposure, account.currency), "Effective leverage", leverage(effectiveLeverage))
                        MetricRow("Deposit", money(account.deposit, account.currency), "Minimum balance at 50% margin", money(minimumBalance, account.currency))
                        MetricRow("Protection", humanProtection(position.protectionRegime), "Break-even", if (position.breakEvenArmed) "ARMED" else "OFF", if (position.breakEvenArmed) BrightGreen else TextSecondary)
                    }
                }
                state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun MetricRow(firstLabel: String, firstValue: String, secondLabel: String, secondValue: String, valueColor: androidx.compose.ui.graphics.Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Metric(firstLabel, firstValue, Modifier.weight(1f), valueColor)
        Metric(secondLabel, secondValue, Modifier.weight(1f), valueColor)
    }
}

private fun sameCondition(first: PriceCondition, second: PriceCondition?): Boolean {
    if (second == null) return false
    return first.name.equals(second.name, true) && first.source.equals(second.source, true) && abs(first.targetPrice - second.targetPrice) <= 1e-6
}

@Composable
private fun ConditionCard(title: String, condition: PriceCondition?, nearest: Boolean) {
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle(title, condition?.source ?: "")
        if (condition == null) { Text("No active price condition", color = TextSecondary); return@AppCard }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(condition.name, color = if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.headlineMedium)
            if (nearest) StatusChip("NEAREST")
        }
        MetricRow("Target price", price(condition.targetPrice), "Distance", "${price(condition.distancePoints)} pts\n(${String.format("%.2f", condition.distancePercent)}%)", if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface)
        MetricRow("Current price", price(condition.currentPrice), "Direction", condition.direction.replaceFirstChar { it.uppercase() })
    }
}

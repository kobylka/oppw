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
import com.oppw.monitor.util.price
import com.oppw.monitor.util.shortDateTime
import com.oppw.monitor.util.timeOnly
import com.oppw.monitor.util.volume
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId
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
                Column(Modifier.fillMaxSize().padding(14.dp)) {
                    AppCard(Modifier.fillMaxWidth()) {
                        Text("No open position", style = MaterialTheme.typography.titleLarge)
                        Text("The app is connected and waiting for the next strategy position.", color = TextSecondary)
                    }
                }
                return
            }
            val account = snapshot.account
            val weekend = isWeekend(state.nowEpochMs)
            val ohPending = !weekend && snapshot.connection.nextAction.equals("OH", true)
            val suppliedConditions = snapshot.conditions.filterNot { it.name.equals("OH", true) && !ohPending }.sortedBy { it.distancePoints }
            val closest = snapshot.closestCondition?.takeUnless { it.name.equals("OH", true) && !ohPending } ?: suppliedConditions.firstOrNull()
            val conditions = suppliedConditions.filterNot { condition -> sameCondition(condition, closest) }
            val minimumBalance = account.deposit * 1.765
            val exposure = account.deposit * 20.0
            val effectiveLeverage = if (account.equity > 0.0) exposure / account.equity else 0.0
            val potentialTakeProfit = position.potentialTakeProfit.takeIf { it > 0.0 }
                ?: conditions.firstOrNull { it.name.equals("OH", true) || it.name.equals("CH", true) }?.targetPrice
                ?: 0.0
            val liveTickAge = liveSourceAge(position.tickAgeSeconds, position.priceTime.ifBlank { snapshot.connection.lastSync }, state.nowEpochMs)

            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
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
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("Volume", volume(position.volume), Modifier.weight(1f))
                            Metric("Open price", price(position.openPrice), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("Current bid", price(position.bid), Modifier.weight(1f), if (position.profit >= 0) BrightGreen else DangerRed)
                            Metric("Current ask", price(position.ask), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("Bid time", timeOnly(position.bidAt.ifBlank { position.priceTime }), Modifier.weight(1f))
                            Metric("Ask time", timeOnly(position.askAt.ifBlank { position.priceTime }), Modifier.weight(1f))
                        }
                        Text("Price age: ${age(liveTickAge)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("Stop loss", price(position.stopLoss), Modifier.weight(1f), DangerRed)
                            Metric("Potential OH/CH target", price(potentialTakeProfit), Modifier.weight(1f), BrightGreen)
                        }
                    }
                }

                if (weekend) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Market closed", "Weekend")
                            Text("The position remains open because the Friday close did not complete. No OH, CH or TO countdown is active while the market is closed.", color = DangerRed)
                        }
                    }
                }

                item { ConditionCard("Closest condition", closest, true) }

                item { SectionTitle("All other conditions", conditions.size.toString()) }
                if (conditions.isEmpty()) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            Text("No conditions supplied by the strategy publisher.", color = TextSecondary)
                        }
                    }
                } else {
                    items(conditions.size, key = { index -> "condition-${conditions[index].name}-$index" }) { index ->
                        val condition = conditions[index]
                        ConditionCard(condition.name, condition, false)
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Risk to stop loss")
                        RiskBar(position.stopLoss, position.openPrice, position.bid)
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            Metric("Unrealized P/L", money(position.profit, account.currency), Modifier.weight(1f), if (position.profit >= 0) BrightGreen else DangerRed)
                            Metric("P/L % leveraged", percent(position.leveragedProfitPercent), Modifier.weight(1f), if (position.leveragedProfitPercent >= 0) BrightGreen else DangerRed)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            Metric("Exposure", money(exposure, account.currency), Modifier.weight(1f))
                            Metric("Effective leverage", leverage(effectiveLeverage), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            Metric("Deposit", money(account.deposit, account.currency), Modifier.weight(1f))
                            Metric("Minimum balance at 50% margin", money(minimumBalance, account.currency), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                            Metric("Protection", humanProtection(position.protectionRegime), Modifier.weight(1f))
                            Metric("Break-even", if (position.breakEvenArmed) "ARMED" else "OFF", Modifier.weight(1f), if (position.breakEvenArmed) BrightGreen else TextSecondary)
                        }
                    }
                }

                state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun ConditionCard(title: String, condition: PriceCondition?, nearest: Boolean) {
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle(title, condition?.source ?: "")
        if (condition == null) {
            Text("No active price condition", color = TextSecondary)
            return@AppCard
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(condition.name, color = if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.headlineMedium)
            if (nearest) StatusChip("NEAREST")
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Metric("Target price", price(condition.targetPrice), Modifier.weight(1f))
            Metric("Distance", "${price(condition.distancePoints)} pts\n(${String.format("%.2f", condition.distancePercent)}%)", Modifier.weight(1f), if (nearest) PrimaryBlue else MaterialTheme.colorScheme.onSurface)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Metric("Current price", price(condition.currentPrice), Modifier.weight(1f))
            Metric("Direction", condition.direction.replaceFirstChar { it.uppercase() }, Modifier.weight(1f))
        }
    }
}


private fun sameCondition(first: PriceCondition, second: PriceCondition?): Boolean {
    if (second == null) return false
    return first.name.trim().equals(second.name.trim(), ignoreCase = true) &&
        first.source.trim().equals(second.source.trim(), ignoreCase = true) &&
        abs(first.targetPrice - second.targetPrice) <= 0.01
}

private fun isWeekend(nowEpochMs: Long): Boolean {
    val day = Instant.ofEpochMilli(nowEpochMs).atZone(ZoneId.of("Europe/Warsaw")).dayOfWeek
    return day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY
}

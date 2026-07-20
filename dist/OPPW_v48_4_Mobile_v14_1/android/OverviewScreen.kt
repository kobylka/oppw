package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.MarketWeekStats
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.AllTimeEquityChart
import com.oppw.monitor.ui.components.EquityChart
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.components.StatusChip
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.age
import com.oppw.monitor.util.countdown
import com.oppw.monitor.util.humanProtection
import com.oppw.monitor.util.leverage
import com.oppw.monitor.util.liveSourceAge
import com.oppw.monitor.util.money
import com.oppw.monitor.util.optionalPercent
import com.oppw.monitor.util.optionalPrice
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.priceHealth
import com.oppw.monitor.util.shortDateTime
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId

@Composable
fun OverviewScreen(state: UiState, onRetry: () -> Unit) {
    when {
        state.loading && state.response == null -> LoadingPanel()
        state.response == null -> ErrorPanel(state.error ?: "No data", onRetry)
        else -> {
            val response = state.response!!
            val snapshot = response.snapshot
            val connection = snapshot.connection
            val account = snapshot.account
            val position = snapshot.position
            val weekend = isWeekend(state.nowEpochMs)
            val heartbeatAge = liveSourceAge(connection.lastUpdateAgeSeconds, response.generatedAt, state.nowEpochMs)
            val lastTickAge = liveSourceAge(connection.us100AgeSeconds, response.generatedAt, state.nowEpochMs)
            val health = priceHealth(lastTickAge)
            val lastTick = connection.lastTick.ifBlank { position?.priceTime?.takeIf { it.isNotBlank() } ?: connection.lastSync }
            val effectivePnlPercent = if (account.balance != 0.0) (position?.profit ?: 0.0) / account.balance * 100.0 else 0.0
            val exposure = position?.exposure?.takeIf { it > 0.0 } ?: if (position != null) account.deposit * 20.0 else 0.0
            val effectiveLeverage = position?.effectiveLeverage?.takeIf { it > 0.0 }
                ?: if (account.balance > 0.0) exposure / account.balance else 0.0
            val phase = if (weekend) "Weekend" else connection.phase
            val regime = if (weekend) "None" else humanProtection(position?.protectionRegime?.ifBlank { null } ?: connection.regime.ifBlank { "None" })
            val nextAction = if (weekend) "None" else connection.nextAction
            val nextActionAt = if (weekend) "" else connection.nextActionAt
            val nextActionLabel = displayNextAction(nextAction, nextActionAt)
            val initialBalance = snapshot.equityCurves.allTime.firstOrNull()?.value ?: account.balance

            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(if (connection.connected) Icons.Outlined.CloudDone else Icons.Outlined.CloudOff, null, tint = if (connection.connected) BrightGreen else DangerRed)
                                Text(if (connection.connected) "Remote DB connected" else "Remote DB unavailable", color = if (connection.connected) BrightGreen else DangerRed)
                            }
                            Text(shortDateTime(response.generatedAt), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("Account: ${connection.accountId}", color = PrimaryBlue)
                            Text("Week: ${connection.week}", color = PrimaryBlue)
                        }
                    }
                }

                item {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        AppCard(Modifier.weight(1f)) {
                            Text("Health:", color = TextSecondary)
                            StatusChip(health, healthTone(health))
                            Text("Heartbeat: ${age(heartbeatAge)}", style = MaterialTheme.typography.bodyMedium)
                            Text("Last tick: ${shortDateTime(lastTick)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                        }
                        AppCard(Modifier.weight(1f)) {
                            Text("Phase", color = TextSecondary)
                            Text(phase, color = PrimaryBlue, style = MaterialTheme.typography.titleMedium)
                            Text("Regime", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                            Text(regime, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Next action", nextActionLabel.ifBlank { "None" })
                        if (nextAction.equals("None", true) || nextActionAt.isBlank()) {
                            Text(if (weekend) "Market is closed. No weekend checks are scheduled." else "No scheduled checks", color = TextSecondary, style = MaterialTheme.typography.titleMedium)
                        } else {
                            Text(countdown(nextActionAt, state.nowEpochMs), color = BrightGreen, style = MaterialTheme.typography.headlineMedium)
                            Text(shortDateTime(nextActionAt), color = TextSecondary)
                        }
                    }
                }

                if (weekend && position != null) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            SectionTitle("Position carried over weekend", "Friday close incomplete")
                            Text(
                                "The position remains open, but the market is closed. OH, CH and TO countdowns are suppressed until trading resumes.",
                                color = DangerRed,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Balance", money(account.balance, account.currency), Modifier.weight(1f))
                            Metric("Equity", money(account.equity, account.currency), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Deposit", money(account.deposit, account.currency), Modifier.weight(1f))
                            Metric("Current P/L", money(position?.profit ?: 0.0, account.currency), Modifier.weight(1f), pnlColor(position?.profit ?: 0.0))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Current P/L %", percent(position?.profitPercent ?: 0.0), Modifier.weight(1f), pnlColor(position?.profitPercent ?: 0.0))
                            Metric("P/L % effective", percent(effectivePnlPercent), Modifier.weight(1f), pnlColor(effectivePnlPercent))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Leverage", position?.strategyLeverage?.let { "${it.toInt()}x" } ?: "—", Modifier.weight(1f))
                            Metric("P/L % leveraged", percent(position?.leveragedProfitPercent ?: 0.0), Modifier.weight(1f), pnlColor(position?.leveragedProfitPercent ?: 0.0))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Effective leverage", leverage(effectiveLeverage), Modifier.weight(1f))
                            Metric("Exposure", money(exposure, account.currency), Modifier.weight(1f))
                        }
                    }
                }

                item { WeekMarketCard("US100 · current week", snapshot.marketStats.currentWeek, currentLabel = "Current price") }
                item { WeekMarketCard("US100 · previous week", snapshot.marketStats.previousWeek, currentLabel = "Final price") }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Equity curve", "daily")
                        EquityChart(snapshot.equityCurves.daily.ifEmpty { snapshot.equityHistory }, account.currency)
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Equity curve", "weekly")
                        EquityChart(snapshot.equityCurves.weekly, account.currency)
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Equity curve", "all time")
                        AllTimeEquityChart(snapshot.equityCurves.allTime, account.currency, initialBalance)
                    }
                }

                state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun WeekMarketCard(title: String, stats: MarketWeekStats?, currentLabel: String) {
    AppCard(Modifier.fillMaxWidth()) {
        SectionTitle(title, stats?.week ?: "No history")
        if (stats == null) {
            Text("No stored market data for this week yet.", color = TextSecondary)
            return@AppCard
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric(currentLabel, optionalPrice(stats.currentPrice), Modifier.weight(1f))
            Metric("Week open", optionalPrice(stats.weekOpen), Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("Weekly high", optionalPrice(stats.weeklyHigh), Modifier.weight(1f))
            Metric("High %", optionalPercent(stats.weeklyHighPercent), Modifier.weight(1f), pnlColor(stats.weeklyHighPercent ?: 0.0))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("Weekly low", optionalPrice(stats.weeklyLow), Modifier.weight(1f))
            Metric("Low %", optionalPercent(stats.weeklyLowPercent), Modifier.weight(1f), pnlColor(stats.weeklyLowPercent ?: 0.0))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("Weekly close", optionalPrice(stats.weeklyClose), Modifier.weight(1f))
            Metric("Close %", optionalPercent(stats.weeklyClosePercent), Modifier.weight(1f), pnlColor(stats.weeklyClosePercent ?: 0.0))
        }
        SectionTitle("Latest day", stats.dailyDate.ifBlank { "—" })
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("Open", optionalPrice(stats.dailyOpen), Modifier.weight(1f))
            Metric("High", optionalPrice(stats.dailyHigh), Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("Low", optionalPrice(stats.dailyLow), Modifier.weight(1f))
            Metric("Close", optionalPrice(stats.dailyClose), Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Metric("High %", optionalPercent(stats.dailyHighPercent), Modifier.weight(1f), pnlColor(stats.dailyHighPercent ?: 0.0))
            Metric("Low %", optionalPercent(stats.dailyLowPercent), Modifier.weight(1f), pnlColor(stats.dailyLowPercent ?: 0.0))
            Metric("Close %", optionalPercent(stats.dailyClosePercent), Modifier.weight(1f), pnlColor(stats.dailyClosePercent ?: 0.0))
        }
    }
}

private fun pnlColor(value: Double): Color = if (value >= 0) BrightGreen else DangerRed
private fun healthTone(value: String): String = when (value.uppercase()) {
    "OK" -> "green"
    "WARNING" -> "warning"
    else -> "blue"
}

private fun isWeekend(nowEpochMs: Long): Boolean {
    val day = Instant.ofEpochMilli(nowEpochMs).atZone(ZoneId.of("Europe/Warsaw")).dayOfWeek
    return day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY
}

private fun displayNextAction(action: String, timestamp: String): String {
    if (action.isBlank() || action.equals("None", true)) return "None"
    if (!action.contains("BUY WINDOW", ignoreCase = true)) return action
    return runCatching {
        val day = java.time.OffsetDateTime.parse(timestamp).dayOfWeek.name.lowercase().replaceFirstChar { it.uppercase() }
        "$day buy window"
    }.getOrDefault(action)
}

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
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.components.Sparkline
import com.oppw.monitor.ui.components.StatusChip
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.countdown
import com.oppw.monitor.util.money
import com.oppw.monitor.util.percent
import com.oppw.monitor.util.shortDateTime

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

            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(if (connection.connected) Icons.Outlined.CloudDone else Icons.Outlined.CloudOff, null, tint = if (connection.connected) BrightGreen else DangerRed)
                                Text(if (connection.connected) "Remote DB connected" else "Remote DB unavailable", color = if (connection.connected) BrightGreen else DangerRed)
                            }
                            Text(shortDateTime(connection.lastSync), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
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
                            Text("Health", color = TextSecondary)
                            StatusChip(connection.health, connection.health)
                        }
                        AppCard(Modifier.weight(1f)) {
                            Text("Phase", color = TextSecondary)
                            Text(connection.phase, color = PrimaryBlue, style = MaterialTheme.typography.titleMedium)
                        }
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Next action", connection.nextAction)
                        Text(countdown(connection.nextActionAt), color = BrightGreen, style = MaterialTheme.typography.headlineMedium)
                        Text(shortDateTime(connection.nextActionAt), color = TextSecondary)
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Deposit", money(account.deposit, account.currency), Modifier.weight(1f))
                            Metric("Equity", money(account.equity, account.currency), Modifier.weight(1f))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Current P/L", money(position?.profit ?: 0.0, account.currency), Modifier.weight(1f), pnlColor(position?.profit ?: 0.0))
                            Metric("Current P/L %", percent(position?.profitPercent ?: 0.0), Modifier.weight(1f), pnlColor(position?.profitPercent ?: 0.0))
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                            Metric("Leverage", position?.strategyLeverage?.let { "${it.toInt()}x" } ?: "—", Modifier.weight(1f))
                            Metric("P/L % leveraged", percent(position?.leveragedProfitPercent ?: 0.0), Modifier.weight(1f), pnlColor(position?.leveragedProfitPercent ?: 0.0))
                        }
                    }
                }

                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Equity", "recent")
                        Sparkline(snapshot.equityHistory.map { it.value })
                    }
                }

                state.error?.let { error ->
                    item { ErrorPanel("Showing cached data. $error", onRetry) }
                }

            }
        }
    }
}

private fun pnlColor(value: Double): Color = if (value >= 0) BrightGreen else DangerRed

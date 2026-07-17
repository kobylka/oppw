package com.oppw.monitor.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.MonitorEvent
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.ErrorPanel
import com.oppw.monitor.ui.components.LoadingPanel
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.Muted
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.ui.theme.WarningAmber
import com.oppw.monitor.util.age
import com.oppw.monitor.util.shortDateTime

@Composable
fun LogsScreen(state: UiState, onRetry: () -> Unit) {
    when {
        state.loading && state.response == null -> LoadingPanel()
        state.response == null -> ErrorPanel(state.error ?: "No data", onRetry)
        else -> {
            val response = state.response!!
            val connection = response.snapshot.connection
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Data freshness", if (connection.connected) "Connected" else "Disconnected")
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("US100", age(connection.us100AgeSeconds), Modifier.weight(1f), freshnessColor(connection.us100AgeSeconds))
                            Metric("QQQ", age(connection.qqqAgeSeconds), Modifier.weight(1f), freshnessColor(connection.qqqAgeSeconds))
                            Metric("Health", connection.health, Modifier.weight(1f), if (connection.health.equals("OK", true)) BrightGreen else WarningAmber)
                        }
                    }
                }
                items(response.events, key = { it.id }) { event -> EventCard(event) }
                if (response.events.isEmpty()) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            Text("No events yet", style = MaterialTheme.typography.titleMedium)
                            Text("Events will appear after the publisher sends them to the API.", color = TextSecondary)
                        }
                    }
                }
                state.error?.let { error -> item { ErrorPanel("Showing cached data. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun EventCard(event: MonitorEvent) {
    val color = eventColor(event)
    AppCard(Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
            Canvas(Modifier.size(10.dp)) { drawCircle(color) }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(event.name, color = color, style = MaterialTheme.typography.titleMedium)
                    Text(shortDateTime(event.time), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                }
                Text(event.message, color = TextSecondary)
                event.result?.let { Text("Result: ${if (it) "TRUE" else "FALSE"}", color = color, style = MaterialTheme.typography.labelMedium) }
            }
        }
    }
}

private fun eventColor(event: MonitorEvent): Color = when {
    event.level.equals("ERROR", true) -> DangerRed
    event.level.equals("WARNING", true) -> WarningAmber
    event.result == true -> BrightGreen
    event.result == false -> Muted
    else -> PrimaryBlue
}

private fun freshnessColor(age: Double?): Color = when {
    age == null -> Muted
    age <= 2.0 -> BrightGreen
    age <= 10.0 -> WarningAmber
    else -> DangerRed
}

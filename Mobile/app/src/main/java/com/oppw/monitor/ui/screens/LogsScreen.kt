package com.oppw.monitor.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.paging.LoadState
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.paging.compose.collectAsLazyPagingItems
import com.oppw.monitor.data.MonitorEvent
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.MainViewModel
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
import com.oppw.monitor.util.isRoutineEvent
import com.oppw.monitor.util.liveSourceAge
import com.oppw.monitor.util.priceHealth
import com.oppw.monitor.util.shortDateTime

@Composable
fun LogsScreen(state: UiState, viewModel: MainViewModel, onRetry: () -> Unit) {
    when {
        state.loading && state.response == null -> LoadingPanel()
        state.response == null -> ErrorPanel(state.error ?: "No data", onRetry)
        state.selectedAccountKey == null -> ErrorPanel("No selected account", onRetry)
        else -> {
            val response = state.response!!
            val connection = response.snapshot.connection
            val us100Age = liveSourceAge(connection.us100AgeSeconds, response.generatedAt, state.nowEpochMs)
            val qqqAge = liveSourceAge(connection.qqqAgeSeconds, response.generatedAt, state.nowEpochMs)
            val health = priceHealth(us100Age)
            val accountKey = state.selectedAccountKey!!
            var buySellOnly by rememberSaveable(accountKey) { mutableStateOf(false) }
            var showRoutineChecks by rememberSaveable(accountKey) { mutableStateOf(false) }
            var selectedEvent by rememberSaveable(accountKey) { mutableStateOf(ALL_EVENTS) }
            val eventName = selectedEvent.takeUnless { it == ALL_EVENTS }
            val hideRoutine = !showRoutineChecks && !buySellOnly
            val flow = remember(accountKey, buySellOnly, hideRoutine, eventName) { viewModel.eventPager(accountKey, buySellOnly, hideRoutine, eventName) }
            val events = flow.collectAsLazyPagingItems()
            val totalMatching by viewModel.logTotalMatching.collectAsStateWithLifecycle()

            LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Data freshness", if (connection.connected) "Connected" else "Disconnected")
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            Metric("US100", age(us100Age), Modifier.weight(1f), freshnessColor(us100Age))
                            Metric("QQQ", age(qqqAge), Modifier.weight(1f), freshnessColor(qqqAge))
                            Metric("Health", health, Modifier.weight(1f), when (health) { "OK" -> BrightGreen; "WARNING" -> WarningAmber; else -> Muted })
                        }
                    }
                }
                item {
                    AppCard(Modifier.fillMaxWidth()) {
                        SectionTitle("Log filters", "${events.itemCount} loaded of $totalMatching · max 500 retained")
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                                Text("Buy/sell events only", style = MaterialTheme.typography.titleMedium)
                                Text("Order-related BUY/SELL events", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                                Text("and POSITION_CLOSED", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                            }
                            Switch(checked = buySellOnly, onCheckedChange = { buySellOnly = it })
                        }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                                Text("Show routine condition checks", style = MaterialTheme.typography.titleMedium)
                                Text("POSITION_IS_OPEN, signal availability, latch, OH, CH and TSL", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
                            }
                            Switch(checked = showRoutineChecks, onCheckedChange = { showRoutineChecks = it })
                        }
                        EventNameSelector(response.eventTypes, selectedEvent) { selectedEvent = it }
                    }
                }

                if (events.loadState.refresh is LoadState.Loading) {
                    item { Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() } }
                }

                items(count = events.itemCount, key = { index -> events[index]?.id ?: "event-$index" }) { index ->
                    events[index]?.let { event ->
                        if (showRoutineChecks || !isRoutineEvent(event)) EventCard(event)
                    }
                }

                when (val append = events.loadState.append) {
                    is LoadState.Loading -> item { Box(Modifier.fillMaxWidth().padding(20.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() } }
                    is LoadState.Error -> item { ErrorPanel("Could not load older logs: ${append.error.message}", events::retry) }
                    else -> Unit
                }

                if (events.itemCount == 0 && events.loadState.refresh !is LoadState.Loading) {
                    item {
                        AppCard(Modifier.fillMaxWidth()) {
                            Text("No matching events", style = MaterialTheme.typography.titleMedium)
                            Text("Change the selected event or disable the buy/sell-only filter.", color = TextSecondary)
                        }
                    }
                }

                val refreshError = events.loadState.refresh as? LoadState.Error
                refreshError?.let { item { ErrorPanel("Could not load logs: ${it.error.message}", events::retry) } }
                state.error?.let { error -> item { ErrorPanel("Showing cached status. $error", onRetry) } }
            }
        }
    }
}

@Composable
private fun EventNameSelector(names: List<String>, selected: String, onSelected: (String) -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
            Text(if (selected == ALL_EVENTS) "All event types" else humanEventName(selected))
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(text = { Text("All event types") }, onClick = { expanded = false; onSelected(ALL_EVENTS) })
            names.filter { it.isNotBlank() }.distinct().sorted().forEach { name ->
                DropdownMenuItem(text = { Text(humanEventName(name)) }, onClick = { expanded = false; onSelected(name) })
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
                    Text(humanEventName(event.name), color = color, style = MaterialTheme.typography.titleMedium)
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

private fun freshnessColor(value: Double?): Color = when {
    value == null -> Muted
    value <= 2.0 -> BrightGreen
    value <= 10.0 -> WarningAmber
    else -> DangerRed
}

private fun humanEventName(name: String): String = when (name.uppercase()) {
    "POSITION_OPEN", "POSITION_IS_OPEN" -> "POSITION_IS_OPEN"
    else -> name
}

private const val ALL_EVENTS = "__ALL__"

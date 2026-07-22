package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.DeleteForever
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.components.AppCard
import com.oppw.monitor.ui.components.Metric
import com.oppw.monitor.ui.components.SectionTitle
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.age
import com.oppw.monitor.util.secondsSinceEpoch

@Composable
fun SettingsScreen(
    state: UiState,
    onRefresh: () -> Unit,
    onUnpair: () -> Unit,
    onServiceDesiredState: (String, Boolean) -> Unit,
) {
    var confirmUnpair by remember { mutableStateOf(false) }
    var pendingServiceCommand by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    val selected = state.accounts.firstOrNull { it.key == state.selectedAccountKey }
    val retrievalAge = secondsSinceEpoch(state.lastSuccessfulFetchEpochMs, state.nowEpochMs)

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Continuous service control")
                val control = state.serviceControl
                if (state.serviceControlLoading && control == null) {
                    CircularProgressIndicator()
                } else if (control == null) {
                    Text(state.serviceControlError ?: "Service status unavailable", color = DangerRed)
                } else {
                    Metric("Master", if (control.master.online) "ONLINE · ${control.master.hostname}" else "OFFLINE")
                    Metric("Backup", if (control.backup.online) "ONLINE · ${control.backup.hostname}" else "OFFLINE")
                    control.roles.forEach { role ->
                        val actual = when {
                            !role.desiredRunning -> "STOPPED BY CONTROL"
                            role.process.running -> "RUNNING ON ${role.activeNodeRole} · PID ${role.process.pid}"
                            role.activeNodeRole.isBlank() -> "NO SUPERVISOR ONLINE"
                            else -> "STARTING ON ${role.activeNodeRole}"
                        }
                        Metric(role.role, actual)
                        OutlinedButton(
                            onClick = { pendingServiceCommand = role.role to !role.desiredRunning },
                            enabled = control.canControl && !state.serviceControlLoading,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(if (role.desiredRunning) "Force stop ${role.role.lowercase()}" else "Force start ${role.role.lowercase()}")
                        }
                    }
                    if (!control.canControl) {
                        Text("This device is read-only. Pair it with service-control permission to enable these controls.", color = TextSecondary)
                    }
                    state.serviceControlError?.let { Text(it, color = DangerRed) }
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Device")
                Metric("Device name", state.deviceName)
                Metric("API", BuildConfig.API_BASE_URL)
                Metric("Last successful HTTPS retrieval", age(retrievalAge))
                Metric("App version", BuildConfig.VERSION_NAME)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Selected account")
                Metric("Name", selected?.displayName ?: "—")
                Metric("Key", selected?.key ?: "—")
                Metric("Type", selected?.accountType ?: "—")
                Metric("Broker account", selected?.brokerAccountId?.ifBlank { "—" } ?: "—")
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Permitted accounts", state.accounts.size.toString())
                state.accounts.forEach { account ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text(account.displayName, style = MaterialTheme.typography.titleMedium)
                            Text(account.key, color = TextSecondary)
                        }
                        Text(account.accountType, color = TextSecondary)
                    }
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Security and alerts")
                Metric("Account protection", "Paired-device HTTPS authorization")
                Metric("Real and Demo access", "Immediate after server authorization")
                Metric("Push alerts", "Position, protection, connection and stale API")
                Text("Firebase values must be configured in local.properties and the backend service account must be enabled for remote alerts.", color = TextSecondary)
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Maintenance")
                OutlinedButton(onClick = onRefresh, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Outlined.Refresh, null)
                    Text("Refresh account and status", Modifier.padding(start = 8.dp))
                }
            }
        }
        item {
            AppCard(Modifier.fillMaxWidth()) {
                SectionTitle("Device authorization")
                Text(
                    "Unpairing revokes this device on the server and deletes the encrypted session from this phone.",
                    color = TextSecondary,
                )
                Button(onClick = { confirmUnpair = true }, modifier = Modifier.fillMaxWidth()) {
                    Icon(Icons.Outlined.DeleteForever, null)
                    Text("Unpair this device", Modifier.padding(start = 8.dp))
                }
            }
        }
    }

    if (confirmUnpair) {
        AlertDialog(
            onDismissRequest = { confirmUnpair = false },
            title = { Text("Unpair this device?") },
            text = { Text("This device will lose access to all monitor accounts and must be paired again.") },
            confirmButton = {
                TextButton(onClick = { confirmUnpair = false; onUnpair() }) { Text("Unpair", color = DangerRed) }
            },
            dismissButton = { TextButton(onClick = { confirmUnpair = false }) { Text("Cancel") } },
        )
    }

    pendingServiceCommand?.let { (role, desiredRunning) ->
        AlertDialog(
            onDismissRequest = { pendingServiceCommand = null },
            title = { Text(if (desiredRunning) "Start $role?" else "Stop $role?") },
            text = {
                Text(
                    "This changes ${selected?.displayName ?: "the selected account"} globally. " +
                        if (desiredRunning) {
                            "The active master, or backup during failover, will start it."
                        } else if (role == "EXECUTOR") {
                            "Both master and backup will keep it stopped. Position management and scheduled trading logic will be suspended; existing broker-side protection remains."
                        } else {
                            "Both master and backup will keep it stopped. Mobile status publishing will be suspended."
                        }
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    pendingServiceCommand = null
                    onServiceDesiredState(role, desiredRunning)
                }) { Text(if (desiredRunning) "Start" else "Stop", color = if (desiredRunning) MaterialTheme.colorScheme.primary else DangerRed) }
            },
            dismissButton = { TextButton(onClick = { pendingServiceCommand = null }) { Text("Cancel") } },
        )
    }
}

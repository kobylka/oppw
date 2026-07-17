package com.oppw.monitor.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ListAlt
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.Assessment
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.PieChartOutline
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.oppw.monitor.data.AuthStatus
import com.oppw.monitor.data.MonitorAccount
import com.oppw.monitor.ui.screens.LogsScreen
import com.oppw.monitor.ui.screens.OverviewScreen
import com.oppw.monitor.ui.screens.PairDeviceScreen
import com.oppw.monitor.ui.screens.PositionScreen
import com.oppw.monitor.ui.screens.SettingsScreen
import com.oppw.monitor.ui.theme.AppBackground
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import kotlinx.coroutines.launch

private data class Tab(val label: String, val icon: ImageVector)

@Composable
fun OppwMonitorApp(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    when (state.authStatus) {
        AuthStatus.CHECKING -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        AuthStatus.UNPAIRED, AuthStatus.PAIRING -> PairDeviceScreen(state, viewModel::pairDevice)
        AuthStatus.PAIRED -> MonitorScaffold(viewModel)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MonitorScaffold(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val selectedAccount = state.accounts.firstOrNull { it.key == state.selectedAccountKey }
    val tabs = listOf(
        Tab("Overview", Icons.Outlined.PieChartOutline),
        Tab("Position", Icons.Outlined.Assessment),
        Tab("Logs", Icons.AutoMirrored.Outlined.ListAlt),
        Tab("Settings", Icons.Outlined.Settings),
    )
    val pagerState = rememberPagerState(pageCount = { tabs.size })
    val scope = androidx.compose.runtime.rememberCoroutineScope()

    Scaffold(
        containerColor = AppBackground,
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("OPPW Monitor", fontWeight = FontWeight.Bold)
                        Text(
                            selectedAccount?.let { "${it.displayName} · ${it.accountType}" } ?: state.deviceName,
                            color = TextSecondary,
                            style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = AppBackground),
                actions = {
                    AccountSwitcher(state.accounts, state.selectedAccountKey, viewModel::selectAccount)
                    IconButton(onClick = viewModel::refresh) { Icon(Icons.Outlined.Refresh, contentDescription = "Refresh") }
                },
            )
        },
        bottomBar = {
            NavigationBar(containerColor = AppBackground) {
                tabs.forEachIndexed { index, tab ->
                    NavigationBarItem(
                        selected = pagerState.currentPage == index,
                        onClick = { scope.launch { pagerState.animateScrollToPage(index) } },
                        icon = { Icon(tab.icon, contentDescription = null) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        HorizontalPager(
            state = pagerState,
            modifier = Modifier.fillMaxSize().padding(padding),
            beyondViewportPageCount = 1,
        ) { page ->
            when (page) {
                0 -> OverviewScreen(state, viewModel::refresh)
                1 -> PositionScreen(state, viewModel::refresh)
                2 -> LogsScreen(state, viewModel::refresh)
                else -> SettingsScreen(state, viewModel::refresh, viewModel::unpairDevice)
            }
        }
    }
}

@Composable
private fun AccountSwitcher(accounts: List<MonitorAccount>, selectedAccountKey: String?, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { expanded = true }, enabled = accounts.isNotEmpty()) {
            Icon(Icons.Outlined.AccountBalanceWallet, contentDescription = "Switch account", tint = PrimaryBlue)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = {
                        Column(Modifier.padding(vertical = 2.dp)) {
                            Text(account.displayName, fontWeight = FontWeight.Medium)
                            Text(
                                listOf(account.accountType, account.brokerAccountId).filter { it.isNotBlank() }.joinToString(" · "),
                                color = TextSecondary,
                                style = androidx.compose.material3.MaterialTheme.typography.labelMedium,
                            )
                        }
                    },
                    leadingIcon = {
                        if (account.key == selectedAccountKey) Icon(Icons.Outlined.CheckCircle, null, tint = PrimaryBlue)
                        else Icon(Icons.Outlined.ExpandMore, null, tint = TextSecondary)
                    },
                    onClick = { expanded = false; onSelect(account.key) },
                )
            }
        }
    }
}

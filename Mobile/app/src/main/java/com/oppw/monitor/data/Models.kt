package com.oppw.monitor.data

data class MonitorAccount(
    val key: String,
    val displayName: String,
    val accountType: String,
    val brokerAccountId: String,
    val isDefault: Boolean,
    val connected: Boolean,
    val health: String,
    val lastSync: String,
)

data class MonitorResponse(
    val generatedAt: String,
    val snapshot: MonitorSnapshot,
    val events: List<MonitorEvent>,
)

data class MonitorSnapshot(
    val connection: ConnectionStatus,
    val account: AccountStatus,
    val position: PositionStatus?,
    val closestCondition: ClosestCondition?,
    val equityHistory: List<EquityPoint>,
)

data class ConnectionStatus(
    val connected: Boolean,
    val lastSync: String,
    val accountId: String,
    val week: String,
    val health: String,
    val phase: String,
    val nextAction: String,
    val nextActionAt: String,
    val us100AgeSeconds: Double?,
    val qqqAgeSeconds: Double?,
)

data class AccountStatus(
    val currency: String,
    val strategyCapital: Double,
    val deposit: Double,
    val balance: Double,
    val equity: Double,
)

data class PositionStatus(
    val symbol: String,
    val side: String,
    val volume: Double,
    val ticket: Long,
    val openedAt: String,
    val openPrice: Double,
    val bid: Double,
    val ask: Double,
    val profit: Double,
    val profitPercent: Double,
    val strategyLeverage: Double,
    val leveragedProfitPercent: Double,
    val exposure: Double,
    val effectiveLeverage: Double,
    val stopLoss: Double,
    val takeProfit: Double,
    val breakEvenArmed: Boolean,
    val protectionRegime: String,
    val activeSlReason: String,
    val activeTpReason: String,
)

data class ClosestCondition(
    val name: String,
    val targetPrice: Double,
    val distancePoints: Double,
    val distancePercent: Double,
    val direction: String,
)

data class EquityPoint(val time: String, val value: Double)

data class MonitorEvent(
    val id: Long,
    val time: String,
    val level: String,
    val name: String,
    val result: Boolean?,
    val message: String,
)

data class UiState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val accountsLoading: Boolean = true,
    val accounts: List<MonitorAccount> = emptyList(),
    val selectedAccountKey: String? = null,
    val response: MonitorResponse? = null,
    val error: String? = null,
)

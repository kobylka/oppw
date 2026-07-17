package com.oppw.monitor.data

enum class AuthStatus { CHECKING, UNPAIRED, PAIRING, PAIRED }

data class MonitorAccount(
    val key: String,
    val displayName: String,
    val accountType: String,
    val brokerAccountId: String,
    val isDefault: Boolean,
    val connected: Boolean,
    val health: String,
    val lastSync: String,
) {
    val isReal: Boolean get() = accountType.equals("REAL", true)
}

data class MonitorResponse(
    val generatedAt: String,
    val snapshot: MonitorSnapshot,
    val eventTypes: List<String>,
)

data class MonitorSnapshot(
    val connection: ConnectionStatus,
    val account: AccountStatus,
    val position: PositionStatus?,
    val closestCondition: PriceCondition?,
    val conditions: List<PriceCondition>,
    val marketStats: MarketStats,
    val equityCurves: EquityCurves,
    val equityHistory: List<EquityPoint>,
)

data class ConnectionStatus(
    val connected: Boolean,
    val lastSync: String,
    val accountId: String,
    val week: String,
    val health: String,
    val phase: String,
    val regime: String,
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
    val priceTime: String,
    val bidAt: String,
    val askAt: String,
    val tickAgeSeconds: Double?,
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

data class PriceCondition(
    val name: String,
    val targetPrice: Double,
    val currentPrice: Double,
    val distancePoints: Double,
    val distancePercent: Double,
    val direction: String,
    val active: Boolean,
    val source: String,
)

data class MarketWeekStats(
    val week: String,
    val currentPrice: Double?,
    val weekOpen: Double?,
    val weekOpenDate: String,
    val weeklyHigh: Double?,
    val weeklyLow: Double?,
    val weeklyClose: Double?,
    val weeklyHighPercent: Double?,
    val weeklyLowPercent: Double?,
    val weeklyClosePercent: Double?,
    val dailyDate: String,
    val dailyOpen: Double?,
    val dailyHigh: Double?,
    val dailyLow: Double?,
    val dailyClose: Double?,
    val dailyHighPercent: Double?,
    val dailyLowPercent: Double?,
    val dailyClosePercent: Double?,
)

data class MarketStats(val currentWeek: MarketWeekStats?, val previousWeek: MarketWeekStats?)
data class EquityCurves(val daily: List<EquityPoint>, val weekly: List<EquityPoint>, val allTime: List<EquityPoint>)
data class EquityPoint(val time: String, val value: Double)

data class MonitorEvent(
    val id: Long,
    val time: String,
    val level: String,
    val name: String,
    val result: Boolean?,
    val message: String,
)

data class EventPage(val events: List<MonitorEvent>, val hasMore: Boolean, val nextBeforeId: Long?, val totalMatching: Int)

data class AnalyticsSummary(
    val totalTrades: Int,
    val closedTrades: Int,
    val openTrades: Int,
    val wins: Int,
    val losses: Int,
    val winRate: Double,
    val netProfit: Double,
    val initialBalance: Double,
    val topUps: Double,
    val withdrawals: Double,
    val netContributions: Double,
    val capitalAdjustedReturnPercent: Double,
    val positiveWeeksPercent: Double,
    val averageWeeklyProfit: Double,
    val totalSlippagePoints: Double,
    val grossProfit: Double,
    val grossLoss: Double,
    val profitFactor: Double,
    val expectancy: Double,
    val medianProfit: Double,
    val averageWin: Double,
    val averageLoss: Double,
    val payoffRatio: Double,
    val averageDurationSeconds: Double,
    val averageMfePoints: Double,
    val averageMaePoints: Double,
    val averageEntrySlippagePoints: Double,
    val averageExitSlippagePoints: Double,
    val captureEfficiencyPercent: Double,
    val edgeRatio: Double,
    val maxDrawdown: Double,
    val recoveryFactor: Double,
    val consistencyScore: Double,
    val maxWinStreak: Int,
    val maxLossStreak: Int,
    val timeInMarketPercent: Double,
    val bestTrade: Double,
    val worstTrade: Double,
)

data class ExitReasonAnalytics(
    val reason: String,
    val trades: Int,
    val winRate: Double,
    val profit: Double,
    val averageProfit: Double,
    val averageMfePoints: Double,
    val averageMaePoints: Double,
)

data class WeeklyAnalytics(
    val week: String,
    val trades: Int,
    val winRate: Double,
    val profit: Double,
    val bestTrade: Double,
    val worstTrade: Double,
    val averageDurationSeconds: Double,
)

data class TradeAnalytics(
    val ticket: Long,
    val symbol: String,
    val side: String,
    val volume: Double,
    val openedAt: String,
    val closedAt: String,
    val openPrice: Double,
    val closePrice: Double,
    val profit: Double,
    val profitPercent: Double,
    val exitReason: String,
    val durationSeconds: Long,
    val mfePoints: Double,
    val maePoints: Double,
    val entrySlippagePoints: Double,
    val exitSlippagePoints: Double,
    val maxProfit: Double,
    val maxDrawdown: Double,
    val closed: Boolean,
)

data class AnalyticsResponse(
    val generatedAt: String,
    val summary: AnalyticsSummary,
    val exitReasons: List<ExitReasonAnalytics>,
    val weekly: List<WeeklyAnalytics>,
    val recentTrades: List<TradeAnalytics>,
)

data class UiState(
    val authStatus: AuthStatus = AuthStatus.CHECKING,
    val deviceName: String = "",
    val pairingError: String? = null,
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val accountsLoading: Boolean = true,
    val accounts: List<MonitorAccount> = emptyList(),
    val selectedAccountKey: String? = null,
    val response: MonitorResponse? = null,
    val analytics: AnalyticsResponse? = null,
    val analyticsLoading: Boolean = false,
    val analyticsError: String? = null,
    val error: String? = null,
    val lastSuccessfulFetchEpochMs: Long = 0L,
    val nowEpochMs: Long = System.currentTimeMillis(),
)

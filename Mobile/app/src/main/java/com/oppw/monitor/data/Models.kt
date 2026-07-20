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
    val potentialPosition: PotentialPosition?,
    val closestCondition: PriceCondition?,
    val conditions: List<PriceCondition>,
    val marketStats: MarketStats,
    val equityCurves: EquityCurves,
    val equityHistory: List<EquityPoint>,
    val strategyDecision: StrategyDecision? = null,
    val lastClosedTrade: LastClosedTrade? = null,
    val execution: ExecutionSnapshot? = null,
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
    val heartbeatStatus: String,
    val lastUpdate: String,
    val lastUpdateAgeSeconds: Double?,
    val lastTick: String,
)

data class AccountStatus(
    val currency: String,
    val strategyCapital: Double,
    val deposit: Double,
    val balance: Double,
    val equity: Double,
)


data class PotentialPosition(
    val available: Boolean,
    val symbol: String,
    val side: String,
    val price: Double,
    val volume: Double,
    val requiredDeposit: Double,
    val balance: Double,
    val effectiveLeverage: Double,
    val strategyLeverage: Double,
    val leverageReason: String,
    val positionNotional: Double,
    val sizingUnits: Int,
    val error: String,
    val generatedAt: String = "",
    val build: String = "",
    val priceSource: String = "",
    val brokerMarginLeverage: Double = 0.0,
    val depositSource: String = "",
    val equity: Double = 0.0,
    val freeMargin: Double = 0.0,
    val freeMarginAfter: Double = 0.0,
    val marginUsagePercent: Double = 0.0,
    val marginLevelAfterPercent: Double = 0.0,
    val previousFullWeekChange: Double = 0.0,
    val previousFullWeekSource: String = "",
    val previousTradeChange: Double = 0.0,
    val previousTradeSource: String = "",
    val potentialStopLossPercent: Double = 0.0,
    val potentialStopLossRatio: Double = 0.0,
    val potentialStopLossPrice: Double = 0.0,
    val potentialStopLossCash: Double = 0.0,
    val accountLossPercentAtStop: Double = 0.0,
    val accountLossCapApplied: Boolean = false,
    val stopLossFormula: String = "",
    val minimumVolumeFloor: Boolean = false,
    val scenarios: List<WhatIfScenario> = emptyList(),
)

data class WhatIfScenario(
    val label: String,
    val underlyingReturnPercent: Double,
    val price: Double,
    val profit: Double,
    val balanceAfter: Double,
    val accountReturnPercent: Double,
)

data class StrategyDecision(
    val decisionId: String,
    val decisionWeek: String = "",
    val recordedAt: String,
    val build: String,
    val parameterHash: String = "",
    val outcome: String,
    val selectedLeverage: Double,
    val leverageReason: String,
    val previousFullWeekChange: Double,
    val previousFullWeekSource: String,
    val previousTradeChange: Double,
    val previousTradeSource: String,
    val error: String,
)

data class ExecutionSnapshot(
    val executionId: String,
    val decisionId: String,
    val positionTicket: Long,
    val scheduledAt: String,
    val startedAt: String,
)

data class LastClosedTrade(
    val positionIdentifier: Long,
    val closedAt: String,
    val exitReason: String,
    val preleverageReturn: Double,
    val preleverageReturnPercent: Double,
    val tradeClass: String  = "",
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
    val potentialTakeProfit: Double,
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
data class EquityPoint(val time: String, val value: Double, val deposits: Double? = null)

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
    val sharpeRatio: Double,
    val sortinoRatio: Double,
    val calmarRatio: Double,
    val omegaRatio: Double,
    val ulcerIndexPercent: Double,
    val valueAtRisk95Percent: Double,
    val expectedShortfall95Percent: Double,
    val riskSampleDays: Int,
    val sharpeAvailable: Boolean = false,
    val sortinoAvailable: Boolean = false,
    val sortinoInfinite: Boolean = false,
    val ratiosAnnualized: Boolean = false,
    val periodsPerYear: Int = 52,
    val ratioSampleTrades: Int = 0,
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
    val balanceBefore: Double = 0.0,
    val tradeReturn: Double? = null,
    val exitReason: String,
    val durationSeconds: Long,
    val mfePoints: Double,
    val maePoints: Double,
    val entrySlippagePoints: Double,
    val exitSlippagePoints: Double,
    val maxProfit: Double,
    val maxDrawdown: Double,
    val closed: Boolean,
    val preleverageReturnPercent: Double = 0.0,
    val tradeClass: String = "",
    val strategyKey: String = "",
    val accountType: String = "",
    val decisionId: String = "",
    val strategyBuild: String = "",
    val parameterHash: String = "",
    val entryLeverage: Double = 0.0,
    val mfePercent: Double = 0.0,
    val maePercent: Double = 0.0,
)

data class TradeClassAnalytics(
    val tradeClass: String = "",
    val trades: Int,
    val profit: Double,
    val averagePreleverageReturnPercent: Double,
    val winRate: Double,
    val profitContributionPercent: Double = 0.0,
    val cumulativeProfit: Double = 0.0,
    val tradeKeys: List<String> = emptyList(),
)

data class TradeDistributionPoint(
    val rank: Int,
    val ticket: Long,
    val strategyKey: String = "",
    val returnPercent: Double,
    val tradeClass: String,
    val exitReason: String,
    val closedAt: String,
    val profit: Double,
)

data class TradeDistribution(
    val sortOrder: String = "BEST_TO_WORST",
    val meanReturnPercent: Double = 0.0,
    val trades: List<TradeDistributionPoint> = emptyList(),
)

data class AnalyticsFilters(
    val scope: String = "SELECTED",
    val leverage: String = "",
    val exitReason: String = "",
    val rollingWeeks: Int = 4,
    val tradeClass: String = "",
)

data class AnalyticsAccountOption(val key: String, val label: String, val type: String)
data class AnalyticsFilterOptions(
    val accounts: List<AnalyticsAccountOption> = emptyList(),
    val leverages: List<Double> = emptyList(),
    val exitReasons: List<String> = emptyList(),
    val availableWeeks: Int = 0,
    val defaultRollingWeeks: Int = 4,
    val effectiveRollingWeeks: Int = 0,
    val classes: List<String> = listOf("A", "B", "C", "D"),
)

data class RollingRatioPoint(
    val endingTradeKey: String,
    val closedAt: String,
    val sampleCount: Int,
    val sharpe: Double?,
    val sortino: Double?,
    val sortinoInfinite: Boolean,
    val tradeKeys: List<String>,
)

data class ConfidenceInterval(
    val key: String,
    val label: String,
    val estimate: Double,
    val lower95: Double,
    val upper95: Double,
    val unit: String,
    val sampleCount: Int,
    val tradeKeys: List<String>,
)

data class ClassDistributionPoint(
    val year: Int,
    val leverage: Double,
    val tradeClass: String,
    val trades: Int,
    val profit: Double,
    val tradeKeys: List<String>,
)

data class DrawdownPoint(
    val index: Int,
    val tradeKey: String,
    val closedAt: String,
    val equityIndex: Double,
    val drawdownPercent: Double,
    val maePercent: Double,
)

data class DrawdownAnalytics(
    val maxDrawdownPercent: Double = 0.0,
    val averageMaePercent: Double = 0.0,
    val series: List<DrawdownPoint> = emptyList(),
    val tradeKeys: List<String> = emptyList(),
)

data class ParameterComparison(
    val build: String,
    val parameterHash: String,
    val firstClosedAt: String,
    val lastClosedAt: String,
    val trades: Int,
    val netProfit: Double,
    val meanAccountReturnPercent: Double,
    val winRate: Double,
    val sharpe: Double?,
    val sortino: Double?,
    val tradeKeys: List<String>,
)

data class BenchmarkPoint(
    val tradeKey: String,
    val closedAt: String,
    val strategyIndex: Double,
    val benchmarkIndex: Double,
)

data class BenchmarkComparison(
    val label: String = "",
    val strategyReturnPercent: Double = 0.0,
    val benchmarkReturnPercent: Double = 0.0,
    val excessReturnPercent: Double = 0.0,
    val sampleCount: Int = 0,
    val series: List<BenchmarkPoint> = emptyList(),
    val tradeKeys: List<String> = emptyList(),
)

data class LatencySummary(
    val sampleCount: Int = 0,
    val medianMs: Double? = null,
    val p95Ms: Double? = null,
    val tradeKeys: List<String> = emptyList(),
)

data class ExecutionStage(
    val stage: String,
    val eventAt: String,
    val result: Boolean?,
    val retcode: String,
    val fillingMode: String,
    val referencePrice: Double,
    val actualPrice: Double,
    val latencyMs: Double?,
    val reason: String,
)

data class ExecutionLifecycle(
    val executionId: String,
    val strategyKey: String,
    val decisionId: String,
    val positionTicket: Long,
    val stages: List<ExecutionStage>,
    val decisionToSendMs: Double?,
    val brokerAcknowledgementMs: Double?,
    val fillMs: Double?,
    val protectionAttachmentMs: Double?,
    val backendPublicationMs: Double?,
    val executorToMobileMs: Double?,
    val entrySlippagePoints: Double?,
    val exitSlippagePoints: Double?,
)

data class ExecutionQuality(
    val lifecycles: List<ExecutionLifecycle> = emptyList(),
    val decisionToSend: LatencySummary = LatencySummary(),
    val brokerAcknowledgement: LatencySummary = LatencySummary(),
    val fill: LatencySummary = LatencySummary(),
    val protectionAttachment: LatencySummary = LatencySummary(),
    val backendPublication: LatencySummary = LatencySummary(),
    val executorToMobile: LatencySummary = LatencySummary(),
    val rejectionRatePercent: Double = 0.0,
    val rejections: Int = 0,
    val orderAttempts: Int = 0,
    val sentOrders: Int = 0,
    val missedExecutionWindows: Int = 0,
    val retcodes: Map<String, Int> = emptyMap(),
    val fillingModes: Map<String, Int> = emptyMap(),
    val tradeKeys: List<String> = emptyList(),
    val rejectionTradeKeys: List<String> = emptyList(),
    val sentTradeKeys: List<String> = emptyList(),
    val missedWindowTradeKeys: List<String> = emptyList(),
    val retcodeTradeKeys: Map<String, List<String>> = emptyMap(),
    val fillingModeTradeKeys: Map<String, List<String>> = emptyMap(),
)

data class AnalyticsResponse(
    val generatedAt: String,
    val filters: AnalyticsFilters = AnalyticsFilters(),
    val filterOptions: AnalyticsFilterOptions = AnalyticsFilterOptions(),
    val summary: AnalyticsSummary,
    val exitReasons: List<ExitReasonAnalytics>,
    val weekly: List<WeeklyAnalytics>,
    val recentTrades: List<TradeAnalytics>,
    val tradeClasses: List<TradeClassAnalytics> = emptyList(),
    val tradeDistribution: TradeDistribution = TradeDistribution(),
    val rolling20: List<RollingRatioPoint> = emptyList(),
    val confidenceIntervals: List<ConfidenceInterval> = emptyList(),
    val classProfitContribution: List<TradeClassAnalytics> = emptyList(),
    val classDistribution: List<ClassDistributionPoint> = emptyList(),
    val drawdown: DrawdownAnalytics = DrawdownAnalytics(),
    val parameterComparison: List<ParameterComparison> = emptyList(),
    val benchmark: BenchmarkComparison = BenchmarkComparison(),
    val executionQuality: ExecutionQuality = ExecutionQuality(),
    val metricSamples: Map<String, List<String>> = emptyMap(),
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
    val analyticsFilters: AnalyticsFilters = AnalyticsFilters(),
    val analyticsLoading: Boolean = false,
    val analyticsError: String? = null,
    val error: String? = null,
    val lastSuccessfulFetchEpochMs: Long = 0L,
    val nowEpochMs: Long = System.currentTimeMillis(),
)

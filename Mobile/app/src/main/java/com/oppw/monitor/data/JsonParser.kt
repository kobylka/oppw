package com.oppw.monitor.data

import com.oppw.monitor.auth.AuthSession
import org.json.JSONArray
import org.json.JSONObject

object JsonParser {
    fun parseAuthSession(raw: String): AuthSession {
        val root = JSONObject(raw)
        requireOk(root)
        val session = root.getJSONObject("session")
        val device = session.getJSONObject("device")
        val allowed = session.optJSONArray("allowedAccounts") ?: JSONArray()
        return AuthSession(
            accessToken = session.getString("accessToken"),
            accessTokenExpiresAt = session.getString("accessTokenExpiresAt"),
            refreshToken = session.getString("refreshToken"),
            refreshTokenExpiresAt = session.getString("refreshTokenExpiresAt"),
            deviceId = device.getString("id"),
            deviceName = device.optString("name", "Android device"),
            allowedAccountKeys = buildList { for (index in 0 until allowed.length()) add(allowed.getJSONObject(index).getString("key")) },
        )
    }

    fun parseAccounts(raw: String): List<MonitorAccount> {
        val root = JSONObject(raw)
        requireOk(root)
        val accounts = root.optJSONArray("accounts") ?: JSONArray()
        return buildList {
            for (i in 0 until accounts.length()) {
                val item = accounts.getJSONObject(i)
                add(MonitorAccount(
                    key = item.optString("key"),
                    displayName = item.optString("displayName", item.optString("key")),
                    accountType = item.optString("accountType", "OTHER"),
                    brokerAccountId = item.optString("brokerAccountId"),
                    isDefault = item.optBoolean("isDefault"),
                    connected = item.optBoolean("connected"),
                    health = item.optString("health", "UNKNOWN"),
                    lastSync = item.optString("lastSync"),
                ))
            }
        }
    }

    fun parseResponse(raw: String): MonitorResponse {
        val root = JSONObject(raw)
        requireOk(root)
        return MonitorResponse(
            generatedAt = root.optString("generatedAt"),
            snapshot = parseSnapshot(root.getJSONObject("snapshot")),
            eventTypes = root.optJSONArray("eventTypes").toStrings(),
        )
    }

    fun parseEventPage(raw: String): EventPage {
        val root = JSONObject(raw)
        requireOk(root)
        return EventPage(
            events = parseEvents(root.optJSONArray("events") ?: JSONArray()),
            hasMore = root.optBoolean("hasMore"),
            nextBeforeId = if (root.has("nextBeforeId") && !root.isNull("nextBeforeId")) root.optLong("nextBeforeId") else null,
            totalMatching = root.optInt("totalMatching"),
        )
    }

    fun parseAnalytics(raw: String): AnalyticsResponse {
        val root = JSONObject(raw)
        requireOk(root)
        val summary = root.getJSONObject("summary")
        val filters = root.optJSONObject("filters") ?: JSONObject()
        val options = root.optJSONObject("filterOptions") ?: JSONObject()
        return AnalyticsResponse(
            generatedAt = root.optString("generatedAt"),
            filters = AnalyticsFilters(
                scope = filters.optString("scope", "SELECTED"), leverage = filters.optString("leverage"),
                exitReason = filters.optString("exitReason"), rollingWeeks = filters.optInt("rollingWeeks", 4), tradeClass = filters.optString("tradeClass"),
            ),
            filterOptions = AnalyticsFilterOptions(
                accounts = buildList {
                    val values = options.optJSONArray("accounts") ?: JSONArray()
                    for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(AnalyticsAccountOption(
                        key = item.optString("key"), label = item.optString("label", item.optString("key")), type = item.optString("type"),
                    )) }
                },
                leverages = options.optJSONArray("leverages").toDoubles(), exitReasons = options.optJSONArray("exitReasons").toStrings(),
                availableWeeks = options.optInt("availableWeeks"), defaultRollingWeeks = options.optInt("defaultRollingWeeks", 4),
                effectiveRollingWeeks = options.optInt("effectiveRollingWeeks"),
                classes = options.optJSONArray("classes").toStrings().ifEmpty { listOf("A", "B", "C", "D") },
            ),
            summary = AnalyticsSummary(
                totalTrades = summary.optInt("totalTrades"), closedTrades = summary.optInt("closedTrades"), openTrades = summary.optInt("openTrades"),
                wins = summary.optInt("wins"), losses = summary.optInt("losses"), winRate = summary.optDouble("winRate"), netProfit = summary.optDouble("netProfit"),
                initialBalance = summary.optDouble("initialBalance"), topUps = summary.optDouble("topUps"), withdrawals = summary.optDouble("withdrawals"),
                netContributions = summary.optDouble("netContributions"), capitalAdjustedReturnPercent = summary.optDouble("capitalAdjustedReturnPercent"),
                positiveWeeksPercent = summary.optDouble("positiveWeeksPercent"), averageWeeklyProfit = summary.optDouble("averageWeeklyProfit"),
                totalSlippagePoints = summary.optDouble("totalSlippagePoints"), grossProfit = summary.optDouble("grossProfit"), grossLoss = summary.optDouble("grossLoss"),
                profitFactor = summary.optDouble("profitFactor"), expectancy = summary.optDouble("expectancy"), medianProfit = summary.optDouble("medianProfit"),
                averageWin = summary.optDouble("averageWin"), averageLoss = summary.optDouble("averageLoss"), payoffRatio = summary.optDouble("payoffRatio"),
                averageDurationSeconds = summary.optDouble("averageDurationSeconds"), averageMfePoints = summary.optDouble("averageMfePoints"), averageMaePoints = summary.optDouble("averageMaePoints"),
                averageEntrySlippagePoints = summary.optDouble("averageEntrySlippagePoints"), averageExitSlippagePoints = summary.optDouble("averageExitSlippagePoints"),
                captureEfficiencyPercent = summary.optDouble("captureEfficiencyPercent"), edgeRatio = summary.optDouble("edgeRatio"), maxDrawdown = summary.optDouble("maxDrawdown"),
                recoveryFactor = summary.optDouble("recoveryFactor"), consistencyScore = summary.optDouble("consistencyScore"), maxWinStreak = summary.optInt("maxWinStreak"),
                maxLossStreak = summary.optInt("maxLossStreak"), timeInMarketPercent = summary.optDouble("timeInMarketPercent"), bestTrade = summary.optDouble("bestTrade"),
                worstTrade = summary.optDouble("worstTrade"), sharpeRatio = summary.optDouble("sharpeRatio"), sortinoRatio = summary.optDouble("sortinoRatio"),
                sharpeAvailable = summary.optBoolean("sharpeAvailable"), sortinoAvailable = summary.optBoolean("sortinoAvailable"), sortinoInfinite = summary.optBoolean("sortinoInfinite"),
                ratiosAnnualized = summary.optBoolean("ratiosAnnualized"), periodsPerYear = summary.optInt("periodsPerYear", 52), ratioSampleTrades = summary.optInt("ratioSampleTrades"),
                calmarRatio = summary.optDouble("calmarRatio"), omegaRatio = summary.optDouble("omegaRatio"), ulcerIndexPercent = summary.optDouble("ulcerIndexPercent"),
                valueAtRisk95Percent = summary.optDouble("valueAtRisk95Percent"), expectedShortfall95Percent = summary.optDouble("expectedShortfall95Percent"), riskSampleDays = summary.optInt("riskSampleDays"),
            ),
            exitReasons = buildList {
                val values = root.optJSONArray("exitReasons") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(ExitReasonAnalytics(
                    reason = item.optString("reason"), trades = item.optInt("trades"), winRate = item.optDouble("winRate"), profit = item.optDouble("profit"),
                    averageProfit = item.optDouble("averageProfit"), averageMfePoints = item.optDouble("averageMfePoints"), averageMaePoints = item.optDouble("averageMaePoints"),
                )) }
            },
            weekly = buildList {
                val values = root.optJSONArray("weekly") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(WeeklyAnalytics(
                    week = item.optString("week"), trades = item.optInt("trades"), winRate = item.optDouble("winRate"), profit = item.optDouble("profit"),
                    bestTrade = item.optDouble("bestTrade"), worstTrade = item.optDouble("worstTrade"), averageDurationSeconds = item.optDouble("averageDurationSeconds"),
                )) }
            },
            recentTrades = parseTrades(root.optJSONArray("recentTrades") ?: JSONArray()),
            tradeClasses = parseTradeClasses(root.optJSONArray("tradeClasses") ?: JSONArray()),
            tradeDistribution = (root.optJSONObject("tradeDistribution") ?: JSONObject()).let { distribution -> TradeDistribution(
                sortOrder = distribution.optString("sortOrder", "BEST_TO_WORST"), meanReturnPercent = distribution.optDouble("meanReturnPercent"),
                trades = buildList {
                    val values = distribution.optJSONArray("trades") ?: JSONArray()
                    for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(TradeDistributionPoint(
                        rank = item.optInt("rank"), ticket = item.optLong("ticket"), strategyKey = item.optString("strategyKey"),
                        returnPercent = item.optDouble("returnPercent"), tradeClass = item.optString("tradeClass"), exitReason = item.optString("exitReason"),
                        closedAt = item.optString("closedAt"), profit = item.optDouble("profit"),
                    )) }
                },
            ) },
            rolling20 = buildList {
                val values = root.optJSONArray("rolling20") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(RollingRatioPoint(
                    endingTradeKey = item.optString("endingTradeKey"), closedAt = item.optString("closedAt"), sampleCount = item.optInt("sampleCount"),
                    sharpe = item.optNullableFiniteDouble("sharpe"), sortino = item.optNullableFiniteDouble("sortino"), sortinoInfinite = item.optBoolean("sortinoInfinite"),
                    tradeKeys = item.optJSONArray("tradeKeys").toStrings(),
                )) }
            },
            confidenceIntervals = buildList {
                val values = root.optJSONArray("confidenceIntervals") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(ConfidenceInterval(
                    key = item.optString("key"), label = item.optString("label"), estimate = item.optDouble("estimate"), lower95 = item.optDouble("lower95"),
                    upper95 = item.optDouble("upper95"), unit = item.optString("unit"), sampleCount = item.optInt("sampleCount"), tradeKeys = item.optJSONArray("tradeKeys").toStrings(),
                )) }
            },
            classProfitContribution = parseTradeClasses(root.optJSONArray("classProfitContribution") ?: JSONArray()),
            classDistribution = buildList {
                val values = root.optJSONArray("classDistribution") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(ClassDistributionPoint(
                    year = item.optInt("year"), leverage = item.optDouble("leverage"), tradeClass = item.optString("tradeClass"), trades = item.optInt("trades"),
                    profit = item.optDouble("profit"), tradeKeys = item.optJSONArray("tradeKeys").toStrings(),
                )) }
            },
            drawdown = (root.optJSONObject("drawdown") ?: JSONObject()).let { value -> DrawdownAnalytics(
                maxDrawdownPercent = value.optDouble("maxDrawdownPercent"), averageMaePercent = value.optDouble("averageMaePercent"),
                series = buildList {
                    val values = value.optJSONArray("series") ?: JSONArray()
                    for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(DrawdownPoint(
                        index = item.optInt("index"), tradeKey = item.optString("tradeKey"), closedAt = item.optString("closedAt"),
                        equityIndex = item.optDouble("equityIndex"), drawdownPercent = item.optDouble("drawdownPercent"), maePercent = item.optDouble("maePercent"),
                    )) }
                }, tradeKeys = value.optJSONArray("tradeKeys").toStrings(),
            ) },
            parameterComparison = buildList {
                val values = root.optJSONArray("parameterComparison") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(ParameterComparison(
                    build = item.optString("build"), parameterHash = item.optString("parameterHash"), firstClosedAt = item.optString("firstClosedAt"), lastClosedAt = item.optString("lastClosedAt"),
                    trades = item.optInt("trades"), netProfit = item.optDouble("netProfit"),
                    meanAccountReturnPercent = item.optDouble("meanAccountReturnPercent"), winRate = item.optDouble("winRate"),
                    sharpe = item.optNullableFiniteDouble("sharpe"), sortino = item.optNullableFiniteDouble("sortino"), tradeKeys = item.optJSONArray("tradeKeys").toStrings(),
                )) }
            },
            benchmark = (root.optJSONObject("benchmark") ?: JSONObject()).let { value -> BenchmarkComparison(
                label = value.optString("label"), strategyReturnPercent = value.optDouble("strategyReturnPercent"), benchmarkReturnPercent = value.optDouble("benchmarkReturnPercent"),
                excessReturnPercent = value.optDouble("excessReturnPercent"), sampleCount = value.optInt("sampleCount"),
                series = buildList {
                    val values = value.optJSONArray("series") ?: JSONArray()
                    for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(BenchmarkPoint(
                        tradeKey = item.optString("tradeKey"), closedAt = item.optString("closedAt"), strategyIndex = item.optDouble("strategyIndex"), benchmarkIndex = item.optDouble("benchmarkIndex"),
                    )) }
                }, tradeKeys = value.optJSONArray("tradeKeys").toStrings(),
            ) },
            executionQuality = parseExecutionQuality(root.optJSONObject("executionQuality") ?: JSONObject()),
            metricSamples = parseStringListMap(root.optJSONObject("metricSamples") ?: JSONObject()),
        )
    }

    private fun parseTrades(values: JSONArray): List<TradeAnalytics> = buildList {
        for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(TradeAnalytics(
            ticket = item.optLong("ticket"), strategyKey = item.optString("strategyKey"), accountType = item.optString("accountType"),
            decisionId = item.optString("decisionId"), strategyBuild = item.optString("strategyBuild"), parameterHash = item.optString("parameterHash"),
            entryLeverage = item.optDouble("entryLeverage"), symbol = item.optString("symbol"), side = item.optString("side"), volume = item.optDouble("volume"),
            openedAt = item.optString("openedAt"), closedAt = item.optString("closedAt"), openPrice = item.optDouble("openPrice"), closePrice = item.optDouble("closePrice"),
            profit = item.optDouble("profit"), profitPercent = item.optDouble("profitPercent", item.optDouble("profit_percent")),
            balanceBefore = item.optDouble("balanceBefore", item.optDouble("balance_before")), tradeReturn = parseExplicitTradeReturn(item),
            exitReason = item.optString("exitReason", item.optString("exit_reason")), durationSeconds = item.optLong("durationSeconds"),
            mfePoints = item.optDouble("mfePoints"), mfePercent = item.optDouble("mfePercent"), maePoints = item.optDouble("maePoints"), maePercent = item.optDouble("maePercent"),
            entrySlippagePoints = item.optDouble("entrySlippagePoints"), exitSlippagePoints = item.optDouble("exitSlippagePoints"),
            maxProfit = item.optDouble("maxProfit"), maxDrawdown = item.optDouble("maxDrawdown"), closed = item.optBoolean("closed"),
            preleverageReturnPercent = item.optDouble("preleverageReturnPercent"), tradeClass = item.optString("tradeClass"),
        )) }
    }

    private fun parseTradeClasses(values: JSONArray): List<TradeClassAnalytics> = buildList {
        for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(TradeClassAnalytics(
            tradeClass = item.optString("tradeClass", item.optString("class")), trades = item.optInt("trades"), profit = item.optDouble("profit"),
            averagePreleverageReturnPercent = item.optDouble("averagePreleverageReturnPercent"), winRate = item.optDouble("winRate"),
            profitContributionPercent = item.optDouble("profitContributionPercent"), cumulativeProfit = item.optDouble("cumulativeProfit"),
            tradeKeys = item.optJSONArray("tradeKeys").toStrings(),
        )) }
    }

    private fun parseExecutionQuality(value: JSONObject): ExecutionQuality = ExecutionQuality(
        lifecycles = buildList {
            val values = value.optJSONArray("lifecycles") ?: JSONArray()
            for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(ExecutionLifecycle(
                executionId = item.optString("executionId"), strategyKey = item.optString("strategyKey"), decisionId = item.optString("decisionId"),
                positionTicket = item.optLong("positionTicket"), stages = buildList {
                    val stages = item.optJSONArray("stages") ?: JSONArray()
                    for (stageIndex in 0 until stages.length()) stages.getJSONObject(stageIndex).let { stage -> add(ExecutionStage(
                        stage = stage.optString("stage"), eventAt = stage.optString("eventAt"),
                        result = if (stage.has("result") && !stage.isNull("result")) stage.optBoolean("result") else null,
                        retcode = if (!stage.has("retcode") || stage.isNull("retcode")) "" else stage.opt("retcode").toString(),
                        fillingMode = stage.optString("fillingMode"), referencePrice = stage.optDouble("referencePrice"), actualPrice = stage.optDouble("actualPrice"),
                        latencyMs = stage.optNullableFiniteDouble("latencyMs"), reason = stage.optString("reason"),
                    )) }
                },
                decisionToSendMs = item.optNullableFiniteDouble("decisionToSendMs"), brokerAcknowledgementMs = item.optNullableFiniteDouble("brokerAcknowledgementMs"),
                fillMs = item.optNullableFiniteDouble("fillMs"), protectionAttachmentMs = item.optNullableFiniteDouble("protectionAttachmentMs"),
                backendPublicationMs = item.optNullableFiniteDouble("backendPublicationMs"), executorToMobileMs = item.optNullableFiniteDouble("executorToMobileMs"),
                entrySlippagePoints = item.optNullableFiniteDouble("entrySlippagePoints"), exitSlippagePoints = item.optNullableFiniteDouble("exitSlippagePoints"),
            )) }
        },
        decisionToSend = parseLatencySummary(value.optJSONObject("decisionToSend")), brokerAcknowledgement = parseLatencySummary(value.optJSONObject("brokerAcknowledgement")),
        fill = parseLatencySummary(value.optJSONObject("fill")), protectionAttachment = parseLatencySummary(value.optJSONObject("protectionAttachment")),
        backendPublication = parseLatencySummary(value.optJSONObject("backendPublication")), executorToMobile = parseLatencySummary(value.optJSONObject("executorToMobile")),
        rejectionRatePercent = value.optDouble("rejectionRatePercent"), rejections = value.optInt("rejections"), orderAttempts = value.optInt("orderAttempts"), sentOrders = value.optInt("sentOrders"),
        missedExecutionWindows = value.optInt("missedExecutionWindows"), retcodes = parseIntMap(value.optJSONObject("retcodes")), fillingModes = parseIntMap(value.optJSONObject("fillingModes")),
        tradeKeys = value.optJSONArray("tradeKeys").toStrings(), rejectionTradeKeys = value.optJSONArray("rejectionTradeKeys").toStrings(),
        sentTradeKeys = value.optJSONArray("sentTradeKeys").toStrings(), missedWindowTradeKeys = value.optJSONArray("missedWindowTradeKeys").toStrings(),
        retcodeTradeKeys = parseStringListMap(value.optJSONObject("retcodeTradeKeys") ?: JSONObject()),
        fillingModeTradeKeys = parseStringListMap(value.optJSONObject("fillingModeTradeKeys") ?: JSONObject()),
    )

    private fun parseLatencySummary(value: JSONObject?): LatencySummary = LatencySummary(
        sampleCount = value?.optInt("sampleCount") ?: 0, medianMs = value?.optNullableFiniteDouble("medianMs"), p95Ms = value?.optNullableFiniteDouble("p95Ms"),
        tradeKeys = value?.optJSONArray("tradeKeys").toStrings(),
    )

    private fun parseIntMap(value: JSONObject?): Map<String, Int> = buildMap {
        val names = value?.names() ?: JSONArray()
        for (i in 0 until names.length()) names.optString(i).takeIf { it.isNotBlank() }?.let { name -> put(name, value?.optInt(name) ?: 0) }
    }

    private fun parseStringListMap(value: JSONObject): Map<String, List<String>> = buildMap {
        val names = value.names() ?: JSONArray()
        for (i in 0 until names.length()) names.optString(i).takeIf { it.isNotBlank() }?.let { name -> put(name, value.optJSONArray(name).toStrings()) }
    }

    private fun parseExecutionSnapshot(json: JSONObject) = ExecutionSnapshot(
        executionId = json.optString("executionId"), decisionId = json.optString("decisionId"), positionTicket = json.optLong("positionTicket"),
        scheduledAt = json.optString("scheduledAt"), startedAt = json.optString("startedAt"),
    )

    private fun parseSnapshot(json: JSONObject): MonitorSnapshot {
        val closest = json.optJSONObject("closestCondition")?.let(::parseCondition)
        val conditions = parseConditions(json.optJSONArray("conditions") ?: JSONArray()).ifEmpty { listOfNotNull(closest) }
        return MonitorSnapshot(
            connection = parseConnection(json.getJSONObject("connection")), account = parseAccount(json.getJSONObject("account")),
            position = json.optJSONObject("position")?.takeUnless { it.has("open") && !it.optBoolean("open") }?.let(::parsePosition),
            potentialPosition = (json.optJSONObject("potentialPosition") ?: json.optJSONObject("potential_position"))?.let(::parsePotentialPosition),
            strategyDecision = (json.optJSONObject("strategyDecision") ?: json.optJSONObject("strategy_decision"))?.let(::parseStrategyDecision),
            lastClosedTrade = (json.optJSONObject("lastClosedTrade") ?: json.optJSONObject("last_closed_trade"))?.let(::parseLastClosedTrade),
            execution = json.optJSONObject("execution")?.let(::parseExecutionSnapshot),
            closestCondition = closest, conditions = conditions, marketStats = parseMarketStats(json.optJSONObject("marketStats")),
            equityCurves = parseEquityCurves(json.optJSONObject("equityCurves")), equityHistory = parseEquity(json.optJSONArray("equityHistory") ?: JSONArray()),
        )
    }

    private fun parseConnection(json: JSONObject) = ConnectionStatus(
        connected = json.optBoolean("connected"), lastSync = json.optString("lastSync"), accountId = json.optString("accountId"), week = json.optString("week"),
        health = json.optString("health", "UNKNOWN"), phase = json.optString("phase", "Unknown"), regime = json.optString("regime", "None"),
        nextAction = json.optString("nextAction", "None"), nextActionAt = json.optString("nextActionAt"),
        us100AgeSeconds = json.optNullableDouble("us100AgeSeconds"), qqqAgeSeconds = json.optNullableDouble("qqqAgeSeconds"),
        heartbeatStatus = json.optString("heartbeatStatus", "UNKNOWN"), lastUpdate = json.optString("lastUpdate", json.optString("lastSync")),
        lastUpdateAgeSeconds = json.optNullableDouble("lastUpdateAgeSeconds"), lastTick = json.optString("lastTick"),
    )

    private fun parseAccount(json: JSONObject) = AccountStatus(
        currency = json.optString("currency", "PLN"), strategyCapital = json.optDouble("strategyCapital"), deposit = json.optDouble("deposit"),
        balance = json.optDouble("balance"), equity = json.optDouble("equity"),
    )

    private fun parsePotentialPosition(json: JSONObject) = PotentialPosition(
        available = json.optBooleanAny("available"), symbol = json.optStringAny("symbol"), side = json.optStringAny("side").ifBlank { "BUY" },
        price = json.optDoubleAny("price", "currentPrice", "current_price"), volume = json.optDoubleAny("volume"),
        requiredDeposit = json.optDoubleAny("requiredDeposit", "required_deposit"), balance = json.optDoubleAny("balance"),
        effectiveLeverage = json.optDoubleAny("effectiveLeverage", "effective_leverage"),
        strategyLeverage = json.optDoubleAny("strategyLeverage", "strategy_leverage", "chosenLeverage", "chosen_leverage"),
        leverageReason = json.optStringAny("leverageReason", "leverage_reason"),
        positionNotional = json.optDoubleAny("positionNotional", "position_notional"), sizingUnits = json.optIntAny("sizingUnits", "sizing_units"),
        error = json.optStringAny("error"), generatedAt = json.optStringAny("generatedAt", "generated_at"), build = json.optStringAny("build"),
        priceSource = json.optStringAny("priceSource", "price_source"), brokerMarginLeverage = json.optDoubleAny("brokerMarginLeverage", "broker_margin_leverage"),
        depositSource = json.optStringAny("depositSource", "deposit_source"), equity = json.optDoubleAny("equity"),
        freeMargin = json.optDoubleAny("freeMargin", "free_margin"), freeMarginAfter = json.optDoubleAny("freeMarginAfter", "free_margin_after"),
        marginUsagePercent = json.optDoubleAny("marginUsagePercent", "margin_usage_percent"), marginLevelAfterPercent = json.optDoubleAny("marginLevelAfterPercent", "margin_level_after_percent"),
        previousFullWeekChange = json.optDoubleAny("previousFullWeekChange", "previous_full_week_change"), previousFullWeekSource = json.optStringAny("previousFullWeekSource", "previous_full_week_source"),
        previousTradeChange = json.optDoubleAny("previousTradeChange", "previous_trade_change"), previousTradeSource = json.optStringAny("previousTradeSource", "previous_trade_source"),
        potentialStopLossPercent = json.optDoubleAny("potentialStopLossPercent", "potential_stop_loss_percent"), potentialStopLossRatio = json.optDoubleAny("potentialStopLossRatio", "potential_stop_loss_ratio"),
        potentialStopLossPrice = json.optDoubleAny("potentialStopLossPrice", "potential_stop_loss_price"), potentialStopLossCash = json.optDoubleAny("potentialStopLossCash", "potential_stop_loss_cash"),
        accountLossPercentAtStop = json.optDoubleAny("accountLossPercentAtStop", "account_loss_percent_at_stop"),
        accountLossCapApplied = json.optBooleanAny("accountLossCapApplied", "account_loss_cap_applied"), stopLossFormula = json.optStringAny("stopLossFormula", "stop_loss_formula"),
        minimumVolumeFloor = json.optBooleanAny("minimumVolumeFloor", "minimum_volume_floor"), scenarios = buildList {
            val values = json.optJSONArray("scenarios") ?: JSONArray()
            for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(WhatIfScenario(
                label = item.optString("label"), underlyingReturnPercent = item.optDouble("underlyingReturnPercent"), price = item.optDouble("price"),
                profit = item.optDouble("profit"), balanceAfter = item.optDouble("balanceAfter"), accountReturnPercent = item.optDouble("accountReturnPercent"),
            )) }
        },
    )

    private fun parseStrategyDecision(json: JSONObject): StrategyDecision {
        val inputs = json.optJSONObject("inputs") ?: JSONObject()
        return StrategyDecision(
            decisionId = json.optString("decisionId"), decisionWeek = json.optString("decisionWeek"), recordedAt = json.optString("recordedAt"), build = json.optString("build"),
            parameterHash = json.optString("parameterHash"), outcome = json.optString("outcome"),
            selectedLeverage = json.optDouble("selectedLeverage"), leverageReason = json.optString("leverageReason"),
            previousFullWeekChange = inputs.optDouble("previousFullWeekChange"), previousFullWeekSource = inputs.optString("previousFullWeekSource"),
            previousTradeChange = inputs.optDouble("previousTradeChange"), previousTradeSource = inputs.optString("previousTradeSource"), error = json.optString("error"),
        )
    }

    private fun parseLastClosedTrade(json: JSONObject) = LastClosedTrade(
        positionIdentifier = json.optLong("positionIdentifier"), closedAt = json.optString("closedAt"), exitReason = json.optString("exitReason"),
        preleverageReturn = json.optDoubleAny("preleverageReturn", "preleverage_return"),
        preleverageReturnPercent = json.optDoubleAny("preleverageReturnPercent", "preleverage_return_percent").takeIf { it != 0.0 }
            ?: json.optDoubleAny("preleverageReturn", "preleverage_return") * 100.0,
        tradeClass = json.optStringAny("tradeClass", "trade_class"),
    )

    private fun parsePosition(json: JSONObject) = PositionStatus(
        symbol = json.optString("symbol"), side = json.optString("side", "BUY"), volume = json.optDouble("volume"), ticket = json.optLong("ticket"),
        openedAt = json.optString("openedAt"), openPrice = json.optDouble("openPrice"), bid = json.optDouble("bid"), ask = json.optDouble("ask"),
        priceTime = json.optString("priceTime", json.optString("bidAt")), bidAt = json.optString("bidAt", json.optString("priceTime")),
        askAt = json.optString("askAt", json.optString("priceTime")), tickAgeSeconds = json.optNullableDouble("tickAgeSeconds"), profit = json.optDouble("profit"),
        profitPercent = json.optDouble("profitPercent"), strategyLeverage = json.optDouble("strategyLeverage"),
        leveragedProfitPercent = json.optDouble("leveragedProfitPercent"), exposure = json.optDouble("exposure"), effectiveLeverage = json.optDouble("effectiveLeverage"),
        stopLoss = json.optDouble("stopLoss"), takeProfit = json.optDouble("takeProfit"), potentialTakeProfit = json.optDouble("potentialTakeProfit"), breakEvenArmed = json.optBoolean("breakEvenArmed"),
        protectionRegime = json.optString("protectionRegime"), activeSlReason = json.optString("activeSlReason"), activeTpReason = json.optString("activeTpReason"),
        breakEvenCheck = json.optJSONObject("breakEvenCheck")?.let(::parseBreakEvenCheck) ?: BreakEvenCheck(),
    )

    private fun parseBreakEvenCheck(json: JSONObject) = BreakEvenCheck(
        status = json.optString("status", "UNAVAILABLE"),
        nextCheckAt = json.optString("nextCheckAt"),
        signalReference = json.optDouble("signalReference"),
        threshold = json.optDouble("threshold"),
        condition = json.optString("condition"),
    )

    private fun parseCondition(json: JSONObject) = PriceCondition(
        name = json.optString("name"), targetPrice = json.optDouble("targetPrice"), currentPrice = json.optDouble("currentPrice"),
        distancePoints = json.optDouble("distancePoints"), distancePercent = json.optDouble("distancePercent"), direction = json.optString("direction"),
        active = json.optBoolean("active", true), source = json.optString("source", "US100"),
    )

    private fun parseConditions(array: JSONArray): List<PriceCondition> = buildList { for (i in 0 until array.length()) add(parseCondition(array.getJSONObject(i))) }
    private fun parseMarketStats(json: JSONObject?): MarketStats = MarketStats(json?.optJSONObject("currentWeek")?.let(::parseMarketWeek), json?.optJSONObject("previousWeek")?.let(::parseMarketWeek))

    private fun parseMarketWeek(json: JSONObject) = MarketWeekStats(
        week = json.optString("week"), currentPrice = json.optNullableDouble("currentPrice"),
        weekOpen = json.optNullableDouble("weekOpen") ?: json.optNullableDouble("fridayOpen"), weekOpenDate = json.optString("weekOpenDate"),
        weeklyHigh = json.optNullableDouble("weeklyHigh"), weeklyLow = json.optNullableDouble("weeklyLow"), weeklyClose = json.optNullableDouble("weeklyClose"),
        weeklyHighPercent = json.optNullableDouble("weeklyHighPercent"), weeklyLowPercent = json.optNullableDouble("weeklyLowPercent"), weeklyClosePercent = json.optNullableDouble("weeklyClosePercent"),
        dailyDate = json.optString("dailyDate", json.optString("dailyLowDate")), dailyOpen = json.optNullableDouble("dailyOpen"), dailyHigh = json.optNullableDouble("dailyHigh"),
        dailyLow = json.optNullableDouble("dailyLow"), dailyClose = json.optNullableDouble("dailyClose"), dailyHighPercent = json.optNullableDouble("dailyHighPercent"),
        dailyLowPercent = json.optNullableDouble("dailyLowPercent"), dailyClosePercent = json.optNullableDouble("dailyClosePercent"),
    )

    private fun parseEquityCurves(json: JSONObject?): EquityCurves = EquityCurves(
        daily = parseEquity(json?.optJSONArray("daily") ?: JSONArray()), weekly = parseEquity(json?.optJSONArray("weekly") ?: JSONArray()), allTime = parseEquity(json?.optJSONArray("allTime") ?: JSONArray()),
    )
    private fun parseEquity(array: JSONArray): List<EquityPoint> = buildList { for (i in 0 until array.length()) array.getJSONObject(i).let { add(EquityPoint(it.optString("time"), it.optDouble("value"), it.optNullableDouble("deposits"))) } }
    private fun parseEvents(array: JSONArray): List<MonitorEvent> = buildList {
        for (i in 0 until array.length()) array.getJSONObject(i).let { item -> add(MonitorEvent(
            id = item.optLong("id"), time = item.optString("time"), level = item.optString("level", "INFO"), name = item.optString("name"),
            result = if (item.has("result") && !item.isNull("result")) item.optBoolean("result") else null, message = item.optString("message"),
        )) }
    }

    private fun parseExplicitTradeReturn(item: JSONObject): Double? {
        val fractionNames = listOf("tradeReturn", "trade_return", "returnFraction", "return_fraction")
        fractionNames.forEach { name ->
            if (item.has(name) && !item.isNull(name)) return item.optDouble(name).takeIf { it.isFinite() }
        }
        val percentNames = listOf("returnPercent", "return_percent")
        percentNames.forEach { name ->
            if (item.has(name) && !item.isNull(name)) return item.optDouble(name).takeIf { it.isFinite() }?.div(100.0)
        }
        return null
    }

    private fun requireOk(root: JSONObject) { if (!root.optBoolean("ok", false)) throw IllegalStateException(root.optString("error", "API returned an error")) }
    private fun JSONObject.optNullableDouble(name: String): Double? = if (!has(name) || isNull(name)) null else optDouble(name)
    private fun JSONObject.optBooleanAny(vararg names: String): Boolean = names.firstNotNullOfOrNull { name -> if (has(name) && !isNull(name)) optBoolean(name) else null } ?: false
    private fun JSONObject.optDoubleAny(vararg names: String): Double = names.firstNotNullOfOrNull { name -> if (has(name) && !isNull(name)) optDouble(name).takeIf { it.isFinite() } else null } ?: 0.0
    private fun JSONObject.optIntAny(vararg names: String): Int = names.firstNotNullOfOrNull { name -> if (has(name) && !isNull(name)) optInt(name) else null } ?: 0
    private fun JSONObject.optStringAny(vararg names: String): String = names.firstNotNullOfOrNull { name -> if (has(name) && !isNull(name)) optString(name).takeIf { it.isNotBlank() } else null } ?: ""
    private fun JSONObject.optNullableFiniteDouble(name: String): Double? = if (!has(name) || isNull(name)) null else optDouble(name).takeIf { it.isFinite() }
    private fun JSONArray?.toDoubles(): List<Double> = if (this == null) emptyList() else buildList { for (i in 0 until length()) optDouble(i).takeIf { it.isFinite() }?.let(::add) }
    private fun JSONArray?.toInts(): List<Int> = if (this == null) emptyList() else buildList { for (i in 0 until length()) add(optInt(i)) }
    private fun JSONArray?.toStrings(): List<String> = if (this == null) emptyList() else buildList { for (i in 0 until length()) add(optString(i)) }
}

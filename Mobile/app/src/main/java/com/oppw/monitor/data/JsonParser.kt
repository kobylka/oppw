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
        return AnalyticsResponse(
            generatedAt = root.optString("generatedAt"),
            summary = AnalyticsSummary(
                totalTrades = summary.optInt("totalTrades"), closedTrades = summary.optInt("closedTrades"), openTrades = summary.optInt("openTrades"),
                wins = summary.optInt("wins"), losses = summary.optInt("losses"), winRate = summary.optDouble("winRate"), netProfit = summary.optDouble("netProfit"),
                initialBalance = summary.optDouble("initialBalance"), topUps = summary.optDouble("topUps"), withdrawals = summary.optDouble("withdrawals"),
                netContributions = summary.optDouble("netContributions"), capitalAdjustedReturnPercent = summary.optDouble("capitalAdjustedReturnPercent"),
                positiveWeeksPercent = summary.optDouble("positiveWeeksPercent"), averageWeeklyProfit = summary.optDouble("averageWeeklyProfit"),
                totalSlippagePoints = summary.optDouble("totalSlippagePoints"), grossProfit = summary.optDouble("grossProfit"), grossLoss = summary.optDouble("grossLoss"), profitFactor = summary.optDouble("profitFactor"),
                expectancy = summary.optDouble("expectancy"), medianProfit = summary.optDouble("medianProfit"), averageWin = summary.optDouble("averageWin"),
                averageLoss = summary.optDouble("averageLoss"), payoffRatio = summary.optDouble("payoffRatio"), averageDurationSeconds = summary.optDouble("averageDurationSeconds"),
                averageMfePoints = summary.optDouble("averageMfePoints"), averageMaePoints = summary.optDouble("averageMaePoints"),
                averageEntrySlippagePoints = summary.optDouble("averageEntrySlippagePoints"), averageExitSlippagePoints = summary.optDouble("averageExitSlippagePoints"),
                captureEfficiencyPercent = summary.optDouble("captureEfficiencyPercent"), edgeRatio = summary.optDouble("edgeRatio"), maxDrawdown = summary.optDouble("maxDrawdown"),
                recoveryFactor = summary.optDouble("recoveryFactor"), consistencyScore = summary.optDouble("consistencyScore"), maxWinStreak = summary.optInt("maxWinStreak"),
                maxLossStreak = summary.optInt("maxLossStreak"), timeInMarketPercent = summary.optDouble("timeInMarketPercent"), bestTrade = summary.optDouble("bestTrade"),
                worstTrade = summary.optDouble("worstTrade"), sharpeRatio = summary.optDouble("sharpeRatio"), sortinoRatio = summary.optDouble("sortinoRatio"),
                calmarRatio = summary.optDouble("calmarRatio"), omegaRatio = summary.optDouble("omegaRatio"), ulcerIndexPercent = summary.optDouble("ulcerIndexPercent"),
                valueAtRisk95Percent = summary.optDouble("valueAtRisk95Percent"), expectedShortfall95Percent = summary.optDouble("expectedShortfall95Percent"),
                riskSampleDays = summary.optInt("riskSampleDays"),
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
            recentTrades = buildList {
                val values = root.optJSONArray("recentTrades") ?: JSONArray()
                for (i in 0 until values.length()) values.getJSONObject(i).let { item -> add(TradeAnalytics(
                    ticket = item.optLong("ticket"), symbol = item.optString("symbol"), side = item.optString("side"), volume = item.optDouble("volume"),
                    openedAt = item.optString("openedAt"), closedAt = item.optString("closedAt"), openPrice = item.optDouble("openPrice"), closePrice = item.optDouble("closePrice"),
                    profit = item.optDouble("profit"), profitPercent = item.optDouble("profitPercent", item.optDouble("profit_percent")),
                    balanceBefore = item.optDouble("balanceBefore", item.optDouble("balance_before")), tradeReturn = parseExplicitTradeReturn(item),
                    exitReason = item.optString("exitReason", item.optString("exit_reason")),
                    durationSeconds = item.optLong("durationSeconds"), mfePoints = item.optDouble("mfePoints"), maePoints = item.optDouble("maePoints"),
                    entrySlippagePoints = item.optDouble("entrySlippagePoints"), exitSlippagePoints = item.optDouble("exitSlippagePoints"),
                    maxProfit = item.optDouble("maxProfit"), maxDrawdown = item.optDouble("maxDrawdown"), closed = item.optBoolean("closed"),
                )) }
            },
        )
    }

    private fun parseSnapshot(json: JSONObject): MonitorSnapshot {
        val closest = json.optJSONObject("closestCondition")?.let(::parseCondition)
        val conditions = parseConditions(json.optJSONArray("conditions") ?: JSONArray()).ifEmpty { listOfNotNull(closest) }
        return MonitorSnapshot(
            connection = parseConnection(json.getJSONObject("connection")), account = parseAccount(json.getJSONObject("account")),
            position = json.optJSONObject("position")?.takeUnless { it.has("open") && !it.optBoolean("open") }?.let(::parsePosition),
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

    private fun parsePosition(json: JSONObject) = PositionStatus(
        symbol = json.optString("symbol"), side = json.optString("side", "BUY"), volume = json.optDouble("volume"), ticket = json.optLong("ticket"),
        openedAt = json.optString("openedAt"), openPrice = json.optDouble("openPrice"), bid = json.optDouble("bid"), ask = json.optDouble("ask"),
        priceTime = json.optString("priceTime", json.optString("bidAt")), bidAt = json.optString("bidAt", json.optString("priceTime")),
        askAt = json.optString("askAt", json.optString("priceTime")), tickAgeSeconds = json.optNullableDouble("tickAgeSeconds"), profit = json.optDouble("profit"),
        profitPercent = json.optDouble("profitPercent"), strategyLeverage = json.optDouble("strategyLeverage"),
        leveragedProfitPercent = json.optDouble("leveragedProfitPercent"), exposure = json.optDouble("exposure"), effectiveLeverage = json.optDouble("effectiveLeverage"),
        stopLoss = json.optDouble("stopLoss"), takeProfit = json.optDouble("takeProfit"), potentialTakeProfit = json.optDouble("potentialTakeProfit"), breakEvenArmed = json.optBoolean("breakEvenArmed"),
        protectionRegime = json.optString("protectionRegime"), activeSlReason = json.optString("activeSlReason"), activeTpReason = json.optString("activeTpReason"),
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
    private fun JSONArray?.toStrings(): List<String> = if (this == null) emptyList() else buildList { for (i in 0 until length()) add(optString(i)) }
}

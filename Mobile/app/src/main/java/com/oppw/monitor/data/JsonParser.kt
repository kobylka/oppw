package com.oppw.monitor.data

import com.oppw.monitor.auth.AuthSession
import org.json.JSONArray
import org.json.JSONObject

object JsonParser {
    fun parseAuthSession(raw: String): AuthSession {
        val root = JSONObject(raw)
        if (!root.optBoolean("ok", false)) throw IllegalStateException(root.optString("error", "API returned an error"))
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
            allowedAccountKeys = buildList {
                for (index in 0 until allowed.length()) add(allowed.getJSONObject(index).getString("key"))
            },
        )
    }

    fun parseAccounts(raw: String): List<MonitorAccount> {
        val root = JSONObject(raw)
        if (!root.optBoolean("ok", false)) throw IllegalStateException(root.optString("error", "API returned an error"))
        val accounts = root.optJSONArray("accounts") ?: JSONArray()
        return buildList {
            for (i in 0 until accounts.length()) {
                val item = accounts.getJSONObject(i)
                add(
                    MonitorAccount(
                        key = item.optString("key"),
                        displayName = item.optString("displayName", item.optString("key")),
                        accountType = item.optString("accountType", "OTHER"),
                        brokerAccountId = item.optString("brokerAccountId"),
                        isDefault = item.optBoolean("isDefault"),
                        connected = item.optBoolean("connected"),
                        health = item.optString("health", "UNKNOWN"),
                        lastSync = item.optString("lastSync"),
                    )
                )
            }
        }
    }

    fun parseResponse(raw: String): MonitorResponse {
        val root = JSONObject(raw)
        if (!root.optBoolean("ok", false)) throw IllegalStateException(root.optString("error", "API returned an error"))
        val snapshot = root.getJSONObject("snapshot")
        return MonitorResponse(
            generatedAt = root.optString("generatedAt"),
            snapshot = parseSnapshot(snapshot),
            events = parseEvents(root.optJSONArray("events") ?: JSONArray()),
        )
    }

    private fun parseSnapshot(json: JSONObject): MonitorSnapshot {
        val closest = json.optJSONObject("closestCondition")?.let(::parseCondition)
        val conditions = parseConditions(json.optJSONArray("conditions") ?: JSONArray()).ifEmpty { listOfNotNull(closest) }
        return MonitorSnapshot(
            connection = parseConnection(json.getJSONObject("connection")),
            account = parseAccount(json.getJSONObject("account")),
            position = json.optJSONObject("position")?.takeUnless { it.has("open") && !it.optBoolean("open") }?.let(::parsePosition),
            closestCondition = closest,
            conditions = conditions,
            marketStats = parseMarketStats(json.optJSONObject("marketStats")),
            equityCurves = parseEquityCurves(json.optJSONObject("equityCurves")),
            equityHistory = parseEquity(json.optJSONArray("equityHistory") ?: JSONArray()),
        )
    }

    private fun parseConnection(json: JSONObject) = ConnectionStatus(
        connected = json.optBoolean("connected"),
        lastSync = json.optString("lastSync"),
        accountId = json.optString("accountId"),
        week = json.optString("week"),
        health = json.optString("health", "UNKNOWN"),
        phase = json.optString("phase", "Unknown"),
        regime = json.optString("regime", "None"),
        nextAction = json.optString("nextAction", "None"),
        nextActionAt = json.optString("nextActionAt"),
        us100AgeSeconds = json.optNullableDouble("us100AgeSeconds"),
        qqqAgeSeconds = json.optNullableDouble("qqqAgeSeconds"),
    )

    private fun parseAccount(json: JSONObject) = AccountStatus(
        currency = json.optString("currency", "PLN"),
        strategyCapital = json.optDouble("strategyCapital", 0.0),
        deposit = json.optDouble("deposit", 0.0),
        balance = json.optDouble("balance", 0.0),
        equity = json.optDouble("equity", 0.0),
    )

    private fun parsePosition(json: JSONObject) = PositionStatus(
        symbol = json.optString("symbol"),
        side = json.optString("side", "BUY"),
        volume = json.optDouble("volume"),
        ticket = json.optLong("ticket"),
        openedAt = json.optString("openedAt"),
        openPrice = json.optDouble("openPrice"),
        bid = json.optDouble("bid"),
        ask = json.optDouble("ask"),
        priceTime = json.optString("priceTime", json.optString("bidAt")),
        bidAt = json.optString("bidAt", json.optString("priceTime")),
        askAt = json.optString("askAt", json.optString("priceTime")),
        tickAgeSeconds = json.optNullableDouble("tickAgeSeconds"),
        profit = json.optDouble("profit"),
        profitPercent = json.optDouble("profitPercent"),
        strategyLeverage = json.optDouble("strategyLeverage"),
        leveragedProfitPercent = json.optDouble("leveragedProfitPercent"),
        exposure = json.optDouble("exposure"),
        effectiveLeverage = json.optDouble("effectiveLeverage"),
        stopLoss = json.optDouble("stopLoss"),
        takeProfit = json.optDouble("takeProfit"),
        breakEvenArmed = json.optBoolean("breakEvenArmed"),
        protectionRegime = json.optString("protectionRegime"),
        activeSlReason = json.optString("activeSlReason"),
        activeTpReason = json.optString("activeTpReason"),
    )

    private fun parseCondition(json: JSONObject) = PriceCondition(
        name = json.optString("name"),
        targetPrice = json.optDouble("targetPrice"),
        currentPrice = json.optDouble("currentPrice"),
        distancePoints = json.optDouble("distancePoints"),
        distancePercent = json.optDouble("distancePercent"),
        direction = json.optString("direction"),
        active = json.optBoolean("active", true),
        source = json.optString("source", "US100"),
    )

    private fun parseConditions(array: JSONArray): List<PriceCondition> = buildList {
        for (i in 0 until array.length()) add(parseCondition(array.getJSONObject(i)))
    }

    private fun parseMarketStats(json: JSONObject?): MarketStats = MarketStats(
        currentWeek = json?.optJSONObject("currentWeek")?.let(::parseMarketWeek),
        previousWeek = json?.optJSONObject("previousWeek")?.let(::parseMarketWeek),
    )

    private fun parseMarketWeek(json: JSONObject) = MarketWeekStats(
        week = json.optString("week"),
        currentPrice = json.optNullableDouble("currentPrice"),
        fridayOpen = json.optNullableDouble("fridayOpen"),
        weeklyLow = json.optNullableDouble("weeklyLow"),
        weeklyLowPercent = json.optNullableDouble("weeklyLowPercent"),
        dailyLow = json.optNullableDouble("dailyLow"),
        dailyLowPercent = json.optNullableDouble("dailyLowPercent"),
        dailyLowDate = json.optString("dailyLowDate"),
    )

    private fun parseEquityCurves(json: JSONObject?): EquityCurves = EquityCurves(
        daily = parseEquity(json?.optJSONArray("daily") ?: JSONArray()),
        weekly = parseEquity(json?.optJSONArray("weekly") ?: JSONArray()),
        allTime = parseEquity(json?.optJSONArray("allTime") ?: JSONArray()),
    )

    private fun parseEquity(array: JSONArray): List<EquityPoint> = buildList {
        for (i in 0 until array.length()) {
            val item = array.getJSONObject(i)
            add(EquityPoint(item.optString("time"), item.optDouble("value")))
        }
    }

    private fun parseEvents(array: JSONArray): List<MonitorEvent> = buildList {
        for (i in 0 until array.length()) {
            val item = array.getJSONObject(i)
            add(
                MonitorEvent(
                    id = item.optLong("id"),
                    time = item.optString("time"),
                    level = item.optString("level", "INFO"),
                    name = item.optString("name"),
                    result = if (item.has("result") && !item.isNull("result")) item.optBoolean("result") else null,
                    message = item.optString("message"),
                )
            )
        }
    }

    private fun JSONObject.optNullableDouble(name: String): Double? = if (!has(name) || isNull(name)) null else optDouble(name)
}

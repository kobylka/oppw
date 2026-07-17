package com.oppw.monitor.data

import org.json.JSONArray
import org.json.JSONObject

object JsonParser {
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

    private fun parseSnapshot(json: JSONObject): MonitorSnapshot = MonitorSnapshot(
        connection = parseConnection(json.getJSONObject("connection")),
        account = parseAccount(json.getJSONObject("account")),
        position = json.optJSONObject("position")?.takeUnless { it.has("open") && !it.optBoolean("open") }?.let(::parsePosition),
        closestCondition = json.optJSONObject("closestCondition")?.let(::parseClosestCondition),
        equityHistory = parseEquity(json.optJSONArray("equityHistory") ?: JSONArray()),
    )

    private fun parseConnection(json: JSONObject) = ConnectionStatus(
        connected = json.optBoolean("connected"),
        lastSync = json.optString("lastSync"),
        accountId = json.optString("accountId"),
        week = json.optString("week"),
        health = json.optString("health", "UNKNOWN"),
        phase = json.optString("phase", "Unknown"),
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

    private fun parseClosestCondition(json: JSONObject) = ClosestCondition(
        name = json.optString("name"),
        targetPrice = json.optDouble("targetPrice"),
        distancePoints = json.optDouble("distancePoints"),
        distancePercent = json.optDouble("distancePercent"),
        direction = json.optString("direction"),
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

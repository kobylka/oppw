package com.oppw.monitor.data

import com.oppw.monitor.auth.AuthSession
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

object JsonParser {
    fun accounts(text: String): List<MonitorAccount> {
        val root = unwrap(JSONObject(text))
        val array = root.optJSONArray("accounts") ?: root.optJSONArray("items") ?: JSONArray()
        return array.objects().map { json ->
            MonitorAccount(
                key = json.string("key", "accountKey", "account_key"),
                displayName = json.string("displayName", "display_name").ifBlank { json.string("key", "accountKey", "account_key") },
                accountType = json.string("accountType", "account_type", "type"),
                brokerAccountId = json.string("brokerAccountId", "broker_account_id", "login"),
                isDefault = json.bool("isDefault", "is_default"),
                health = json.string("health").ifBlank { "UNKNOWN" },
            )
        }.filter { it.key.isNotBlank() }
    }

    fun monitor(text: String): MonitorResponse {
        val root = unwrap(JSONObject(text))
        val snapshot = root.optJSONObject("snapshot") ?: root
        val connection = snapshot.optJSONObject("connection") ?: JSONObject()
        val account = snapshot.optJSONObject("account") ?: JSONObject()
        val positionJson = snapshot.optJSONObject("position")?.takeUnless { it.optBoolean("open", true).not() }
        val conditions = (snapshot.optJSONArray("conditions") ?: JSONArray()).objects().map(::condition)
        val closest = snapshot.optJSONObject("closestCondition")?.let(::condition)
        val market = snapshot.optJSONObject("marketStats") ?: JSONObject()
        val curves = snapshot.optJSONObject("equityCurves") ?: JSONObject()
        return MonitorResponse(
            generatedAt = root.string("generatedAt", "generated_at"),
            snapshot = MonitorSnapshot(
                connection = ConnectionStatus(
                    connected = connection.bool("connected"),
                    lastSync = connection.string("lastSync", "last_sync"),
                    account = connection.string("account", "accountId"),
                    week = connection.string("week"),
                    health = connection.string("health").ifBlank { "UNKNOWN" },
                    phase = connection.string("phase").ifBlank { "Unknown" },
                    regime = connection.string("regime", "protectionRegime").ifBlank { "Unknown" },
                    nextAction = connection.string("nextAction", "next_action").ifBlank { "None" },
                    nextActionAt = connection.string("nextActionAt", "next_action_at"),
                    us100AgeSeconds = connection.numberOrNull("us100AgeSeconds", "us100_age_seconds"),
                    qqqAgeSeconds = connection.numberOrNull("qqqAgeSeconds", "qqq_age_seconds"),
                    heartbeatStatus = connection.string("heartbeatStatus", "heartbeat_status").ifBlank { "UNKNOWN" },
                    lastUpdate = connection.string("lastUpdate", "last_update").ifBlank { connection.string("lastSync", "last_sync") },
                    lastUpdateAgeSeconds = connection.numberOrNull("lastUpdateAgeSeconds", "last_update_age_seconds"),
                    lastTick = connection.string("lastTick", "last_tick"),
                ),
                account = AccountStatus(
                    currency = account.string("currency"),
                    deposit = account.number("deposit", "margin"),
                    balance = account.number("balance"),
                    equity = account.number("equity"),
                    strategyCapital = account.number("strategyCapital", "strategy_capital", "capital"),
                ),
                position = positionJson?.let(::position),
                closestCondition = closest,
                conditions = conditions,
                marketStats = MarketStats(marketWeek(market.optJSONObject("currentWeek")), marketWeek(market.optJSONObject("previousWeek"))),
                equityCurves = EquityCurves(equity(curves.optJSONArray("daily")), equity(curves.optJSONArray("weekly")), equity(curves.optJSONArray("allTime") ?: curves.optJSONArray("all_time"))),
            ),
            eventTypes = (root.optJSONArray("eventTypes") ?: root.optJSONArray("event_types") ?: JSONArray()).strings(),
        )
    }

    fun events(text: String): List<MonitorEvent> {
        val root = unwrap(JSONObject(text))
        val array = root.optJSONArray("events") ?: root.optJSONArray("items") ?: JSONArray()
        return array.objects().map { json ->
            val details = when (val raw = json.opt("details")) { is JSONObject -> raw.toString(); is JSONArray -> raw.toString(); else -> raw?.toString().orEmpty() }
            MonitorEvent(
                id = json.long("id", "eventId"),
                time = json.string("time", "createdAt", "created_at", "capturedAt"),
                name = json.string("name", "event", "eventName").ifBlank { "EVENT" },
                message = json.string("message", "text").ifBlank { details },
                result = json.booleanOrNull("result"),
                severity = json.string("severity", "level").ifBlank { "INFO" },
                category = json.string("category", "kind", "type"),
                details = details,
            )
        }
    }

    fun analytics(text: String): AnalyticsResponse {
        val root = unwrap(JSONObject(text))
        val summary = root.optJSONObject("summary") ?: root
        val tradeArray = root.optJSONArray("trades") ?: root.optJSONArray("closedTrades") ?: root.optJSONArray("closed_trades") ?: JSONArray()
        val trades = tradeArray.objects().map(::trade)
        return AnalyticsResponse(
            generatedAt = root.string("generatedAt", "generated_at"),
            summary = AnalyticsSummary(
                closedTrades = summary.int("closedTrades", "closed_trades", "tradeCount", "trade_count").takeIf { it > 0 } ?: trades.count { it.closed || it.closedAt.isNotBlank() },
                wins = summary.int("wins", "winningTrades", "winning_trades"),
                losses = summary.int("losses", "losingTrades", "losing_trades"),
                winRatePercent = summary.percentOrNull("winRatePercent", "win_rate_percent", "winRate", "win_rate"),
                profitFactor = summary.numberOrNull("profitFactor", "profit_factor"),
                expectancy = summary.numberOrNull("expectancy"),
                payoffRatio = summary.numberOrNull("payoffRatio", "payoff_ratio"),
                maxDrawdownPercent = summary.percentOrNull("maxDrawdownPercent", "max_drawdown_percent", "maxDrawdown", "max_drawdown"),
                recoveryFactor = summary.numberOrNull("recoveryFactor", "recovery_factor"),
                calmarRatio = summary.numberOrNull("calmarRatio", "calmar_ratio"),
                omegaRatio = summary.numberOrNull("omegaRatio", "omega_ratio"),
                ulcerIndexPercent = summary.percentOrNull("ulcerIndexPercent", "ulcer_index_percent"),
                valueAtRisk95Percent = summary.percentOrNull("valueAtRisk95Percent", "value_at_risk_95_percent", "var95Percent"),
                expectedShortfall95Percent = summary.percentOrNull("expectedShortfall95Percent", "expected_shortfall_95_percent", "es95Percent"),
            ),
            trades = trades,
        )
    }

    fun session(text: String): AuthSession {
        val root = unwrap(JSONObject(text))
        val accessSeconds = root.long("accessExpiresIn", "access_expires_in", "expiresIn", "expires_in")
        val refreshSeconds = root.long("refreshExpiresIn", "refresh_expires_in")
        val now = System.currentTimeMillis()
        return AuthSession(
            accessToken = root.string("accessToken", "access_token", "token"),
            refreshToken = root.string("refreshToken", "refresh_token"),
            deviceId = root.string("deviceId", "device_id"),
            accessExpiresAtEpochMs = root.long("accessExpiresAtEpochMs", "access_expires_at_ms").takeIf { it > 0 } ?: if (accessSeconds > 0) now + accessSeconds * 1000 else 0L,
            refreshExpiresAtEpochMs = root.long("refreshExpiresAtEpochMs", "refresh_expires_at_ms").takeIf { it > 0 } ?: if (refreshSeconds > 0) now + refreshSeconds * 1000 else 0L,
        ).also { require(it.accessToken.isNotBlank()) { "Pairing response did not contain an access token" } }
    }

    private fun position(json: JSONObject) = PositionStatus(
        symbol = json.string("symbol").ifBlank { "US100" }, side = json.string("side", "type").ifBlank { "BUY" }, volume = json.number("volume"), ticket = json.long("ticket"), openedAt = json.string("openedAt", "opened_at", "openTime"),
        openPrice = json.number("openPrice", "open_price", "priceOpen"), bid = json.number("bid"), ask = json.number("ask"), bidTime = json.string("bidTime", "bid_time"), askTime = json.string("askTime", "ask_time"), priceTime = json.string("priceTime", "price_time"),
        profit = json.number("profit", "pnl"), profitPercent = json.percent("profitPercent", "profit_percent", "pnlPercent"), leverage = json.number("leverage", "effectiveLeverage"), leveragedProfitPercent = json.percent("leveragedProfitPercent", "leveraged_profit_percent"), exposure = json.number("exposure", "notional"), exposurePercent = json.percent("exposurePercent", "exposure_percent"),
        stopLoss = json.number("stopLoss", "stop_loss", "sl"), takeProfit = json.number("takeProfit", "take_profit", "tp"), targetPrice = json.number("targetPrice", "target_price", "ohChTarget"), breakEvenArmed = json.bool("breakEvenArmed", "break_even_armed", "breakEven"), protectionRegime = json.string("protectionRegime", "protection_regime", "regime"), stopReason = json.string("stopReason", "stop_reason", "slReason"), exitLatch = json.string("exitLatch", "exit_latch"),
    )

    private fun condition(json: JSONObject) = PriceCondition(
        name = json.string("name", "condition").ifBlank { "Condition" },
        targetPrice = json.numberOrNull("targetPrice", "target_price", "price"), currentPrice = json.numberOrNull("currentPrice", "current_price"), distancePoints = json.numberOrNull("distancePoints", "distance_points", "distance"), distancePercent = json.percentOrNull("distancePercent", "distance_percent"), direction = json.string("direction"), active = json.optBoolean("active", true), source = json.string("source", "symbol"), detail = json.string("detail", "description"),
    )

    private fun marketWeek(json: JSONObject?) = MarketWeekStats(
        week = json?.string("week").orEmpty(), currentPrice = json?.numberOrNull("currentPrice", "current_price"), weekOpen = json?.numberOrNull("weekOpen", "week_open"), weeklyHigh = json?.numberOrNull("weeklyHigh", "weekly_high"), weeklyLow = json?.numberOrNull("weeklyLow", "weekly_low"), weeklyClose = json?.numberOrNull("weeklyClose", "weekly_close"), weeklyHighPercent = json?.percentOrNull("weeklyHighPercent", "weekly_high_percent"), weeklyLowPercent = json?.percentOrNull("weeklyLowPercent", "weekly_low_percent"), weeklyClosePercent = json?.percentOrNull("weeklyClosePercent", "weekly_close_percent"), dailyDate = json?.string("dailyDate", "daily_date").orEmpty(), dailyOpen = json?.numberOrNull("dailyOpen", "daily_open"), dailyHigh = json?.numberOrNull("dailyHigh", "daily_high"), dailyLow = json?.numberOrNull("dailyLow", "daily_low"), dailyClose = json?.numberOrNull("dailyClose", "daily_close"),
    )

    private fun equity(array: JSONArray?): List<EquityPoint> = (array ?: JSONArray()).objects().mapNotNull { json ->
        val time = json.string("time", "date", "capturedAt", "captured_at")
        val value = json.numberOrNull("value", "equity") ?: return@mapNotNull null
        EquityPoint(time, value, json.numberOrNull("deposits", "deposit", "deposited"))
    }

    private fun trade(json: JSONObject): ClosedTrade {
        val profit = json.numberOrNull("profit", "realizedProfit", "realized_profit", "pnl", "profitAmount")
        val balanceBefore = json.numberOrNull("balanceBefore", "balance_before", "entryBalance", "capitalBefore", "capital_before")
        val explicitFraction = json.numberOrNull("tradeReturn", "trade_return", "returnFraction", "return_fraction", "return")
        val explicitPercent = json.numberOrNull("returnPercent", "return_percent", "profitPercent", "profit_percent", "pnlPercent", "pnl_percent")
        val inferred = when {
            profit != null && balanceBefore != null && abs(balanceBefore) > 1e-12 -> profit / balanceBefore
            explicitFraction != null -> if (abs(explicitFraction) > 1.5) explicitFraction / 100.0 else explicitFraction
            explicitPercent != null -> explicitPercent / 100.0
            else -> null
        }
        val closedAt = json.string("closedAt", "closed_at", "closeTime", "close_time", "exitTime", "exit_time")
        val status = json.string("status")
        return ClosedTrade(
            id = json.long("id", "tradeId"), openedAt = json.string("openedAt", "opened_at", "openTime", "open_time"), closedAt = closedAt, exitReason = json.string("exitReason", "exit_reason", "reason"), profit = profit, balanceBefore = balanceBefore, returnFraction = inferred,
            openPrice = json.numberOrNull("openPrice", "open_price"), closePrice = json.numberOrNull("closePrice", "close_price"), leverage = json.numberOrNull("leverage"), status = status,
            closed = json.bool("closed", "isClosed", "is_closed") || closedAt.isNotBlank() || status.equals("CLOSED", true),
        )
    }

    private fun unwrap(root: JSONObject): JSONObject = when {
        root.optJSONObject("data") != null -> root.getJSONObject("data")
        root.optJSONObject("result") != null -> root.getJSONObject("result")
        else -> root
    }
}

private fun JSONArray.objects(): List<JSONObject> = buildList { for (index in 0 until length()) optJSONObject(index)?.let(::add) }
private fun JSONArray.strings(): List<String> = buildList { for (index in 0 until length()) optString(index).takeIf(String::isNotBlank)?.let(::add) }
private fun JSONObject.first(keys: Array<out String>): Any? = keys.firstNotNullOfOrNull { key -> takeIf { has(key) && !isNull(key) }?.opt(key) }
private fun JSONObject.string(vararg keys: String): String = first(keys)?.toString()?.takeUnless { it == "null" }.orEmpty()
private fun JSONObject.numberOrNull(vararg keys: String): Double? = first(keys)?.let { value -> when (value) { is Number -> value.toDouble(); else -> value.toString().toDoubleOrNull() } }?.takeIf(Double::isFinite)
private fun JSONObject.number(vararg keys: String): Double = numberOrNull(*keys) ?: 0.0
private fun JSONObject.long(vararg keys: String): Long = first(keys)?.let { value -> when (value) { is Number -> value.toLong(); else -> value.toString().toLongOrNull() } } ?: 0L
private fun JSONObject.int(vararg keys: String): Int = long(*keys).toInt()
private fun JSONObject.bool(vararg keys: String): Boolean = first(keys)?.let { value -> when (value) { is Boolean -> value; is Number -> value.toInt() != 0; else -> value.toString().equals("true", true) || value.toString() == "1" } } ?: false
private fun JSONObject.booleanOrNull(vararg keys: String): Boolean? = first(keys)?.let { value -> when (value) { is Boolean -> value; is Number -> value.toInt() != 0; else -> value.toString().lowercase().takeIf { it == "true" || it == "false" }?.toBooleanStrictOrNull() } }
private fun JSONObject.percentOrNull(vararg keys: String): Double? = numberOrNull(*keys)
private fun JSONObject.percent(vararg keys: String): Double = percentOrNull(*keys) ?: 0.0

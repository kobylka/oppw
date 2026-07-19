package com.oppw.monitor.data

import android.content.Context
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.auth.ApiException
import com.oppw.monitor.auth.AuthSession
import com.oppw.monitor.auth.AuthenticationRequiredException
import com.oppw.monitor.auth.SecureSessionStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.time.OffsetDateTime
import javax.net.ssl.HttpsURLConnection

class StatusApiClient(context: Context, private val baseUrl: String = BuildConfig.API_BASE_URL) {
    private val sessionStore = SecureSessionStore(context.applicationContext)
    private val refreshMutex = Mutex()

    fun hasSession(): Boolean = sessionStore.load() != null
    fun currentDeviceName(): String? = sessionStore.load()?.deviceName

    suspend fun pair(pairingCode: String, deviceName: String): AuthSession {
        val response = execute("POST", "auth/pair.php", JSONObject().put("pairingCode", pairingCode).put("deviceName", deviceName).toString())
        requireSuccess(response)
        return JsonParser.parseAuthSession(response.body).also(sessionStore::save)
    }

    suspend fun unpair() {
        try { authenticatedRequest("POST", "auth/unpair.php", "{}") } finally { sessionStore.clear() }
    }

    fun clearSession() = sessionStore.clear()
    suspend fun fetchAccounts(): List<MonitorAccount> = JsonParser.parseAccounts(authenticatedRequest("GET", "accounts.php").body)

    suspend fun fetchStatus(accountKey: String): MonitorResponse {
        val response = JsonParser.parseResponse(authenticatedRequest("GET", "status.php?account=${encode(accountKey)}").body)
        val execution = response.snapshot.execution
        if (execution != null && execution.executionId.isNotBlank()) runCatching {
            authenticatedRequest("POST", "mobile-receipt.php", JSONObject()
                .put("accountKey", accountKey)
                .put("executionId", execution.executionId)
                .put("decisionId", execution.decisionId)
                .put("positionTicket", execution.positionTicket)
                .put("snapshotGeneratedAt", response.generatedAt)
                .put("receivedAt", OffsetDateTime.now().toString())
                .toString())
        }
        return response
    }

    suspend fun fetchAnalytics(accountKey: String, filters: AnalyticsFilters): AnalyticsResponse {
        val query = buildString {
            append("analytics.php?account=").append(encode(accountKey))
            append("&scope=").append(encode(filters.scope))
            if (filters.leverage.isNotBlank()) append("&leverage=").append(encode(filters.leverage))
            if (filters.exitReason.isNotBlank()) append("&exit_reason=").append(encode(filters.exitReason))
            if (filters.year.isNotBlank()) append("&year=").append(encode(filters.year))
            if (filters.tradeClass.isNotBlank()) append("&class=").append(encode(filters.tradeClass))
        }
        return JsonParser.parseAnalytics(authenticatedRequest("GET", query).body)
    }

    suspend fun fetchEvents(accountKey: String, beforeId: Long?, limit: Int, buySellOnly: Boolean, hideRoutine: Boolean, eventName: String?): EventPage {
        val query = buildString {
            append("events.php?account=").append(encode(accountKey))
            append("&limit=").append(limit.coerceIn(20, 150))
            if (beforeId != null && beforeId > 0) append("&before_id=").append(beforeId)
            if (buySellOnly) append("&buy_sell_only=1")
            if (hideRoutine) append("&hide_routine=1")
            if (!eventName.isNullOrBlank()) append("&event_name=").append(encode(eventName))
        }
        return JsonParser.parseEventPage(authenticatedRequest("GET", query).body)
    }

    suspend fun registerPushToken(token: String) {
        if (token.isBlank() || !hasSession()) return
        authenticatedRequest("POST", "push/register.php", JSONObject().put("token", token).put("platform", "ANDROID").put("appVersion", BuildConfig.VERSION_NAME).toString())
    }

    suspend fun unregisterPushToken(token: String? = null) {
        if (!hasSession()) return
        authenticatedRequest("POST", "push/unregister.php", JSONObject().apply { if (!token.isNullOrBlank()) put("token", token) }.toString())
    }

    private suspend fun authenticatedRequest(method: String, path: String, body: String? = null): HttpResponse {
        var session = ensureSession(false)
        var response = execute(method, path, body, session.accessToken)
        if (response.code == 401) {
            session = ensureSession(true, session.accessToken)
            response = execute(method, path, body, session.accessToken)
        }
        if (response.code == 401) {
            sessionStore.clear()
            throw AuthenticationRequiredException()
        }
        requireSuccess(response)
        return response
    }

    private suspend fun ensureSession(forceRefresh: Boolean, staleAccessToken: String? = null): AuthSession = refreshMutex.withLock {
        val current = sessionStore.load() ?: throw AuthenticationRequiredException()
        if (staleAccessToken != null && current.accessToken != staleAccessToken) return@withLock current
        if (!forceRefresh && !expiresSoon(current.accessTokenExpiresAt)) return@withLock current
        if (expiresAtOrBeforeNow(current.refreshTokenExpiresAt)) {
            sessionStore.clear()
            throw AuthenticationRequiredException("Device session expired. Pair the app again.")
        }
        val response = execute("POST", "auth/refresh.php", JSONObject().put("deviceId", current.deviceId).put("refreshToken", current.refreshToken).toString())
        if (response.code == 401) {
            sessionStore.clear()
            throw AuthenticationRequiredException("Device authorization was revoked or expired.")
        }
        requireSuccess(response)
        JsonParser.parseAuthSession(response.body).also(sessionStore::save)
    }

    private fun expiresSoon(value: String): Boolean = runCatching { OffsetDateTime.parse(value).toInstant().epochSecond <= java.time.Instant.now().epochSecond + 30 }.getOrDefault(true)
    private fun expiresAtOrBeforeNow(value: String): Boolean = runCatching { !OffsetDateTime.parse(value).toInstant().isAfter(java.time.Instant.now()) }.getOrDefault(true)
    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.toString())

    private suspend fun execute(method: String, path: String, body: String? = null, accessToken: String? = null): HttpResponse = withContext(Dispatchers.IO) {
        require(baseUrl.startsWith("https://")) { "OPPW_API_BASE_URL must use HTTPS" }
        require(!baseUrl.contains("example.com")) { "Set OPPW_API_BASE_URL in local.properties" }
        val url = URL((if (baseUrl.endsWith('/')) baseUrl else "$baseUrl/") + path)
        val connection = (url.openConnection() as HttpsURLConnection).apply {
            requestMethod = method
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (!accessToken.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $accessToken")
            useCaches = false
            if (body != null) { doOutput = true; outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) } }
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            HttpResponse(code, stream?.bufferedReader()?.use { it.readText() }.orEmpty())
        } finally { connection.disconnect() }
    }

    private fun requireSuccess(response: HttpResponse) {
        if (response.code in 200..299) return
        val message = runCatching { JSONObject(response.body).optString("error") }.getOrNull().orEmpty()
        throw ApiException(response.code, message.ifBlank { "HTTP ${response.code}: ${response.body.take(250)}" })
    }

    private data class HttpResponse(val code: Int, val body: String)
}

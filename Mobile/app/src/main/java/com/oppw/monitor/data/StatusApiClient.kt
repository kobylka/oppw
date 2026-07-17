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

class StatusApiClient(
    context: Context,
    private val baseUrl: String = BuildConfig.API_BASE_URL,
) {
    private val sessionStore = SecureSessionStore(context.applicationContext)
    private val refreshMutex = Mutex()

    fun hasSession(): Boolean = sessionStore.load() != null
    fun currentDeviceName(): String? = sessionStore.load()?.deviceName

    suspend fun pair(pairingCode: String, deviceName: String): AuthSession {
        val response = execute(
            method = "POST",
            path = "auth/pair.php",
            body = JSONObject().put("pairingCode", pairingCode).put("deviceName", deviceName).toString(),
        )
        requireSuccess(response)
        return JsonParser.parseAuthSession(response.body).also(sessionStore::save)
    }

    suspend fun unpair() {
        try {
            authenticatedRequest("POST", "auth/unpair.php", "{}")
        } finally {
            sessionStore.clear()
        }
    }

    fun clearSession() = sessionStore.clear()

    suspend fun fetchAccounts(): List<MonitorAccount> = JsonParser.parseAccounts(authenticatedRequest("GET", "accounts.php").body)

    suspend fun fetchStatus(accountKey: String): MonitorResponse {
        require(accountKey.isNotBlank()) { "Account key is empty" }
        val encoded = URLEncoder.encode(accountKey, StandardCharsets.UTF_8.toString())
        return JsonParser.parseResponse(authenticatedRequest("GET", "status.php?account=$encoded").body)
    }

    private suspend fun authenticatedRequest(method: String, path: String, body: String? = null): HttpResponse {
        var session = ensureSession(forceRefresh = false)
        var response = execute(method, path, body, session.accessToken)
        if (response.code == 401) {
            session = ensureSession(forceRefresh = true, staleAccessToken = session.accessToken)
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

        val response = execute(
            method = "POST",
            path = "auth/refresh.php",
            body = JSONObject().put("deviceId", current.deviceId).put("refreshToken", current.refreshToken).toString(),
        )
        if (response.code == 401) {
            sessionStore.clear()
            throw AuthenticationRequiredException("Device authorization was revoked or expired.")
        }
        requireSuccess(response)
        JsonParser.parseAuthSession(response.body).also(sessionStore::save)
    }

    private fun expiresSoon(value: String): Boolean = runCatching {
        OffsetDateTime.parse(value).toInstant().epochSecond <= java.time.Instant.now().epochSecond + 30
    }.getOrDefault(true)

    private fun expiresAtOrBeforeNow(value: String): Boolean = runCatching {
        !OffsetDateTime.parse(value).toInstant().isAfter(java.time.Instant.now())
    }.getOrDefault(true)

    private suspend fun execute(method: String, path: String, body: String? = null, accessToken: String? = null): HttpResponse = withContext(Dispatchers.IO) {
        require(baseUrl.startsWith("https://")) { "OPPW_API_BASE_URL must use HTTPS" }
        require(!baseUrl.contains("example.com")) { "Set OPPW_API_BASE_URL in local.properties" }
        val url = URL(baseUrl.ensureTrailingSlash() + path)
        require(url.protocol.equals("https", ignoreCase = true)) { "Only HTTPS endpoints are allowed" }
        val connection = (url.openConnection() as HttpsURLConnection).apply {
            requestMethod = method
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            if (!accessToken.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $accessToken")
            useCaches = false
            if (body != null) {
                doOutput = true
                outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
        }
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val responseBody = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            HttpResponse(code, responseBody)
        } finally {
            connection.disconnect()
        }
    }

    private fun requireSuccess(response: HttpResponse) {
        if (response.code in 200..299) return
        val message = runCatching { JSONObject(response.body).optString("error") }.getOrNull().orEmpty()
        throw ApiException(response.code, message.ifBlank { "HTTP ${response.code}: ${response.body.take(250)}" })
    }

    private fun String.ensureTrailingSlash(): String = if (endsWith('/')) this else "$this/"
    private data class HttpResponse(val code: Int, val body: String)
}

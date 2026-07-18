package com.oppw.monitor.data

import android.content.Context
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.auth.AuthSession
import com.oppw.monitor.auth.SecureSessionStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class ApiException(message: String, val statusCode: Int = 0) : RuntimeException(message)
class AuthenticationRequiredException(message: String) : RuntimeException(message)

class ApiClient(context: Context) {
    private val sessionStore = SecureSessionStore(context)
    private val baseUrl = BuildConfig.API_BASE_URL.trim().let { if (it.endsWith('/')) it else "$it/" }
    private val staticToken = BuildConfig.API_TOKEN.trim()

    fun hasSession(): Boolean = staticToken.isNotBlank() || sessionStore.load()?.accessToken?.isNotBlank() == true
    fun clearSession() = sessionStore.clear()

    suspend fun pair(code: String, deviceName: String): AuthSession = withContext(Dispatchers.IO) {
        val body = JSONObject().put("code", code).put("pairingCode", code).put("pairing_code", code).put("deviceName", deviceName).put("device_name", deviceName).toString()
        val text = rawRequest("auth/pair.php", "POST", body, null, retryAuth = false)
        JsonParser.session(text).also(sessionStore::save)
    }

    suspend fun unpair() = withContext(Dispatchers.IO) {
        runCatching { rawRequest("auth/unpair.php", "POST", JSONObject().put("deviceId", sessionStore.load()?.deviceId.orEmpty()).toString(), token(), retryAuth = true) }
        sessionStore.clear()
    }

    suspend fun get(path: String): String = withContext(Dispatchers.IO) { rawRequest(path, "GET", null, token(), retryAuth = true) }

    private fun token(): String? = staticToken.ifBlank { sessionStore.load()?.accessToken.orEmpty() }.takeIf(String::isNotBlank)

    private fun rawRequest(path: String, method: String, body: String?, bearer: String?, retryAuth: Boolean): String {
        val connection = (URL(baseUrl + path.removePrefix("/")).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 20_000
            useCaches = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "OPPW-Monitor-Android/10.0.0")
            bearer?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
        }
        val status = connection.responseCode
        if (status == HttpURLConnection.HTTP_UNAUTHORIZED && retryAuth && staticToken.isBlank() && refreshSession()) {
            connection.disconnect()
            return rawRequest(path, method, body, token(), retryAuth = false)
        }
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        connection.disconnect()
        if (status == HttpURLConnection.HTTP_UNAUTHORIZED) throw AuthenticationRequiredException(errorMessage(text, "Authentication required"))
        if (status !in 200..299) throw ApiException(errorMessage(text, "HTTP $status"), status)
        return text
    }

    private fun refreshSession(): Boolean {
        val old = sessionStore.load() ?: return false
        if (old.refreshToken.isBlank()) return false
        return runCatching {
            val body = JSONObject().put("refreshToken", old.refreshToken).put("refresh_token", old.refreshToken).put("deviceId", old.deviceId).put("device_id", old.deviceId).toString()
            val text = rawRequest("auth/refresh.php", "POST", body, null, retryAuth = false)
            sessionStore.save(JsonParser.session(text))
            true
        }.getOrElse { false }
    }

    private fun errorMessage(text: String, fallback: String): String = runCatching {
        val root = JSONObject(text)
        root.optString("error").ifBlank { root.optString("message") }.ifBlank { fallback }
    }.getOrDefault(text.take(300).ifBlank { fallback })

    companion object {
        fun query(value: String): String = URLEncoder.encode(value, Charsets.UTF_8.name())
    }
}

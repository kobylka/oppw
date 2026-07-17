package com.oppw.monitor.data

import com.oppw.monitor.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class StatusApiClient(
    private val baseUrl: String = BuildConfig.API_BASE_URL,
    private val token: String = BuildConfig.API_TOKEN,
) {
    suspend fun fetchAccounts(): List<MonitorAccount> = request("accounts.php", JsonParser::parseAccounts)

    suspend fun fetchStatus(accountKey: String): MonitorResponse {
        require(accountKey.isNotBlank()) { "Account key is empty" }
        val encoded = URLEncoder.encode(accountKey, StandardCharsets.UTF_8.toString())
        return request("status.php?account=$encoded", JsonParser::parseResponse)
    }

    private suspend fun <T> request(path: String, parser: (String) -> T): T = withContext(Dispatchers.IO) {
        require(baseUrl.startsWith("https://")) { "OPPW_API_BASE_URL must use HTTPS" }
        require(!baseUrl.contains("example.com")) { "Set OPPW_API_BASE_URL in local.properties" }
        require(token.isNotBlank()) { "Set OPPW_API_TOKEN in local.properties" }

        val url = URL(baseUrl.ensureTrailingSlash() + path)
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Authorization", "Bearer $token")
            useCaches = false
        }

        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream.bufferedReader().use { it.readText() }
            if (code !in 200..299) throw IllegalStateException("HTTP $code: ${body.take(250)}")
            parser(body)
        } finally {
            connection.disconnect()
        }
    }

    private fun String.ensureTrailingSlash(): String = if (endsWith('/')) this else "$this/"
}

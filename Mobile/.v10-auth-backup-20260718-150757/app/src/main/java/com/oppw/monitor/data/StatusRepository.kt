package com.oppw.monitor.data

import android.content.Context
import com.oppw.monitor.auth.AuthSession

class StatusRepository(context: Context) {
    private val api = StatusApiClient(context)
    fun hasSession(): Boolean = api.hasSession()
    fun currentDeviceName(): String? = api.currentDeviceName()
    fun clearSession() = api.clearSession()
    suspend fun pair(pairingCode: String, deviceName: String): AuthSession = api.pair(pairingCode, deviceName)
    suspend fun unpair() = api.unpair()
    suspend fun accounts(): List<MonitorAccount> = api.fetchAccounts()
    suspend fun refresh(accountKey: String): MonitorResponse = api.fetchStatus(accountKey)
    suspend fun analytics(accountKey: String): AnalyticsResponse = api.fetchAnalytics(accountKey)
    suspend fun events(accountKey: String, beforeId: Long?, limit: Int, buySellOnly: Boolean, hideRoutine: Boolean, eventName: String?): EventPage = api.fetchEvents(accountKey, beforeId, limit, buySellOnly, hideRoutine, eventName)
    suspend fun registerPushToken(token: String) = api.registerPushToken(token)
    suspend fun unregisterPushToken(token: String? = null) = api.unregisterPushToken(token)
}

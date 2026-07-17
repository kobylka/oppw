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
}

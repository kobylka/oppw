package com.oppw.monitor.data

class StatusRepository(private val api: StatusApiClient = StatusApiClient()) {
    suspend fun accounts(): List<MonitorAccount> = api.fetchAccounts()
    suspend fun refresh(accountKey: String): MonitorResponse = api.fetchStatus(accountKey)
}

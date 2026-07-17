package com.oppw.monitor.ui

import android.app.Application
import android.content.Context
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.auth.AuthenticationRequiredException
import com.oppw.monitor.data.AuthStatus
import com.oppw.monitor.data.MonitorAccount
import com.oppw.monitor.data.StatusRepository
import com.oppw.monitor.data.UiState
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = StatusRepository(application)
    private val preferences = application.getSharedPreferences("oppw_monitor", Context.MODE_PRIVATE)
    private val _uiState = MutableStateFlow(UiState(deviceName = repository.currentDeviceName() ?: defaultDeviceName()))
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
    private var pollingJob: Job? = null
    private var clockJob: Job? = null
    private var lastAccountsRefreshMs = 0L

    init {
        startClock()
        if (repository.hasSession()) {
            _uiState.value = _uiState.value.copy(authStatus = AuthStatus.PAIRED)
            startPolling()
        } else {
            _uiState.value = _uiState.value.copy(authStatus = AuthStatus.UNPAIRED, loading = false, accountsLoading = false)
        }
    }

    fun pairDevice(pairingCode: String, deviceName: String) {
        if (_uiState.value.authStatus == AuthStatus.PAIRING) return
        val normalizedCode = pairingCode.trim().uppercase()
        val normalizedName = deviceName.trim().ifBlank(::defaultDeviceName)
        _uiState.value = _uiState.value.copy(authStatus = AuthStatus.PAIRING, pairingError = null, deviceName = normalizedName)
        viewModelScope.launch {
            runCatching { repository.pair(normalizedCode, normalizedName) }
                .onSuccess { session ->
                    _uiState.value = UiState(authStatus = AuthStatus.PAIRED, deviceName = session.deviceName)
                    startPolling()
                }
                .onFailure { error ->
                    _uiState.value = UiState(
                        authStatus = AuthStatus.UNPAIRED,
                        loading = false,
                        accountsLoading = false,
                        deviceName = normalizedName,
                        pairingError = error.message ?: error::class.java.simpleName,
                    )
                }
        }
    }

    fun unpairDevice() {
        pollingJob?.cancel()
        pollingJob = null
        viewModelScope.launch {
            runCatching { repository.unpair() }
            preferences.edit().remove(PREF_SELECTED_ACCOUNT).apply()
            lastAccountsRefreshMs = 0L
            _uiState.value = UiState(
                authStatus = AuthStatus.UNPAIRED,
                loading = false,
                accountsLoading = false,
                deviceName = defaultDeviceName(),
            )
        }
    }

    fun refresh() {
        if (_uiState.value.authStatus != AuthStatus.PAIRED) return
        viewModelScope.launch { load(manual = true, forceAccounts = true) }
    }

    fun selectAccount(accountKey: String) {
        val current = _uiState.value
        if (current.authStatus != AuthStatus.PAIRED || accountKey == current.selectedAccountKey) return
        if (current.accounts.none { it.key == accountKey }) return
        preferences.edit().putString(PREF_SELECTED_ACCOUNT, accountKey).apply()
        _uiState.value = current.copy(loading = true, selectedAccountKey = accountKey, response = null, error = null)
        viewModelScope.launch { load(manual = true, forceAccounts = false) }
    }

    private fun startClock() {
        clockJob?.cancel()
        clockJob = viewModelScope.launch {
            while (true) {
                _uiState.value = _uiState.value.copy(nowEpochMs = System.currentTimeMillis())
                delay(1_000L)
            }
        }
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (true) {
                load(manual = false, forceAccounts = false)
                delay(BuildConfig.POLL_INTERVAL_MS)
            }
        }
    }

    private suspend fun load(manual: Boolean, forceAccounts: Boolean) {
        val previous = _uiState.value
        if (previous.authStatus != AuthStatus.PAIRED) return
        _uiState.value = previous.copy(loading = previous.response == null, refreshing = manual, error = null)

        var accounts = previous.accounts
        var selectedKey = previous.selectedAccountKey
        runCatching {
            accounts = loadAccountsIfNeeded(previous.accounts, forceAccounts)
            require(accounts.isNotEmpty()) { "No permitted monitor accounts are configured for this device" }
            selectedKey = resolveSelectedAccount(accounts, previous.selectedAccountKey)
            _uiState.value = _uiState.value.copy(accountsLoading = false, accounts = accounts, selectedAccountKey = selectedKey)
            repository.refresh(requireNotNull(selectedKey))
        }.onSuccess { response ->
            val now = System.currentTimeMillis()
            _uiState.value = UiState(
                authStatus = AuthStatus.PAIRED,
                deviceName = previous.deviceName,
                accountsLoading = false,
                accounts = accounts,
                selectedAccountKey = selectedKey,
                response = response,
                lastSuccessfulFetchEpochMs = now,
                nowEpochMs = now,
            )
        }.onFailure { error ->
            if (error is AuthenticationRequiredException) {
                pollingJob?.cancel()
                repository.clearSession()
                _uiState.value = UiState(
                    authStatus = AuthStatus.UNPAIRED,
                    loading = false,
                    accountsLoading = false,
                    deviceName = defaultDeviceName(),
                    pairingError = error.message,
                )
            } else {
                val current = _uiState.value
                _uiState.value = current.copy(
                    loading = false,
                    refreshing = false,
                    accountsLoading = accounts.isEmpty(),
                    accounts = accounts,
                    selectedAccountKey = selectedKey,
                    error = error.message ?: error::class.java.simpleName,
                )
            }
        }
    }

    private suspend fun loadAccountsIfNeeded(current: List<MonitorAccount>, force: Boolean): List<MonitorAccount> {
        val now = System.currentTimeMillis()
        if (!force && current.isNotEmpty() && now - lastAccountsRefreshMs < ACCOUNTS_REFRESH_MS) return current
        return repository.accounts().also { lastAccountsRefreshMs = now }
    }

    private fun resolveSelectedAccount(accounts: List<MonitorAccount>, stateSelection: String?): String {
        val saved = preferences.getString(PREF_SELECTED_ACCOUNT, null)
        val selected = sequenceOf(stateSelection, saved)
            .filterNotNull()
            .firstOrNull { key -> accounts.any { it.key == key } }
            ?: accounts.firstOrNull { it.isDefault }?.key
            ?: accounts.first().key
        preferences.edit().putString(PREF_SELECTED_ACCOUNT, selected).apply()
        return selected
    }

    private fun defaultDeviceName(): String = listOf(Build.MANUFACTURER, Build.MODEL)
        .map { it.trim() }
        .filter { it.isNotBlank() }
        .distinct()
        .joinToString(" ")
        .ifBlank { "Android device" }

    override fun onCleared() {
        pollingJob?.cancel()
        clockJob?.cancel()
        super.onCleared()
    }

    companion object {
        private const val PREF_SELECTED_ACCOUNT = "selected_account"
        private const val ACCOUNTS_REFRESH_MS = 60_000L
    }
}

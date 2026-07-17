package com.oppw.monitor.ui

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.oppw.monitor.BuildConfig
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
    private val repository = StatusRepository()
    private val preferences = application.getSharedPreferences("oppw_monitor", Context.MODE_PRIVATE)
    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
    private var pollingJob: Job? = null
    private var lastAccountsRefreshMs = 0L

    init {
        startPolling()
    }

    fun refresh() {
        viewModelScope.launch { load(manual = true, forceAccounts = true) }
    }

    fun selectAccount(accountKey: String) {
        val current = _uiState.value
        if (accountKey == current.selectedAccountKey) return
        if (current.accounts.none { it.key == accountKey }) return

        preferences.edit().putString(PREF_SELECTED_ACCOUNT, accountKey).apply()
        _uiState.value = current.copy(
            loading = true,
            selectedAccountKey = accountKey,
            response = null,
            error = null,
        )
        viewModelScope.launch { load(manual = true, forceAccounts = false) }
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
        _uiState.value = previous.copy(
            loading = previous.response == null,
            refreshing = manual,
            error = null,
        )

        var accounts = previous.accounts
        var selectedKey = previous.selectedAccountKey
        runCatching {
            accounts = loadAccountsIfNeeded(previous.accounts, forceAccounts)
            require(accounts.isNotEmpty()) { "No enabled monitor accounts are configured" }
            selectedKey = resolveSelectedAccount(accounts, previous.selectedAccountKey)
            _uiState.value = _uiState.value.copy(
                accountsLoading = false,
                accounts = accounts,
                selectedAccountKey = selectedKey,
            )
            repository.refresh(requireNotNull(selectedKey))
        }.onSuccess { response ->
            _uiState.value = UiState(
                accountsLoading = false,
                accounts = accounts,
                selectedAccountKey = selectedKey,
                response = response,
            )
        }.onFailure { error ->
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

    private suspend fun loadAccountsIfNeeded(current: List<MonitorAccount>, force: Boolean): List<MonitorAccount> {
        val now = System.currentTimeMillis()
        if (!force && current.isNotEmpty() && now - lastAccountsRefreshMs < ACCOUNTS_REFRESH_MS) return current
        val accounts = repository.accounts()
        lastAccountsRefreshMs = now
        return accounts
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

    companion object {
        private const val PREF_SELECTED_ACCOUNT = "selected_account"
        private const val ACCOUNTS_REFRESH_MS = 60_000L
    }
}

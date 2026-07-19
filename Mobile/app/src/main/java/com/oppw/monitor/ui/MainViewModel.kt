package com.oppw.monitor.ui

import android.app.Application
import android.content.Context
import android.os.Build
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.auth.AuthenticationRequiredException
import com.oppw.monitor.data.AnalyticsFilters
import com.oppw.monitor.data.AuthStatus
import com.oppw.monitor.data.EventsPagingSource
import com.oppw.monitor.data.MonitorAccount
import com.oppw.monitor.data.MonitorEvent
import com.oppw.monitor.data.StatusRepository
import com.oppw.monitor.data.UiState
import com.oppw.monitor.notifications.NotificationHelper
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = StatusRepository(application)
    private val preferences = application.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val _uiState = MutableStateFlow(UiState(deviceName = repository.currentDeviceName() ?: defaultDeviceName()))
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
    private val _logTotalMatching = MutableStateFlow(0)
    val logTotalMatching: StateFlow<Int> = _logTotalMatching.asStateFlow()
    private var pollingJob: Job? = null
    private var clockJob: Job? = null
    private var lastAccountsRefreshMs = 0L
    private var staleNotificationShown = false
    private var statusMonitoringStartedMs = System.currentTimeMillis()

    init {
        startClock()
        if (repository.hasSession()) {
            _uiState.value = _uiState.value.copy(authStatus = AuthStatus.PAIRED)
            startPolling()
            registerPushToken()
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
                    statusMonitoringStartedMs = System.currentTimeMillis()
                    _uiState.value = UiState(authStatus = AuthStatus.PAIRED, deviceName = session.deviceName)
                    registerPushToken()
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
            runCatching { repository.unregisterPushToken() }
            runCatching { repository.unpair() }
            NotificationHelper.cancelApiStale(getApplication<Application>())
            preferences.edit().clear().apply()
            lastAccountsRefreshMs = 0L
            statusMonitoringStartedMs = System.currentTimeMillis()
            _uiState.value = UiState(authStatus = AuthStatus.UNPAIRED, loading = false, accountsLoading = false, deviceName = defaultDeviceName())
        }
    }

    fun refresh() {
        if (_uiState.value.authStatus != AuthStatus.PAIRED) return
        viewModelScope.launch { load(manual = true, forceAccounts = true) }
    }

    fun requestAccountSelection(accountKey: String) {
        val current = _uiState.value
        if (current.authStatus != AuthStatus.PAIRED || accountKey == current.selectedAccountKey) return
        if (current.accounts.none { it.key == accountKey }) return
        applyAccountSelection(accountKey)
    }

    fun loadAnalytics(force: Boolean = false) {
        val current = _uiState.value
        val key = current.selectedAccountKey ?: return
        if (!force && current.analytics != null) return
        val filters = current.analyticsFilters
        _uiState.value = current.copy(analyticsLoading = true, analyticsError = null)
        viewModelScope.launch {
            runCatching { repository.analytics(key, filters) }
                .onSuccess { analytics -> _uiState.value = _uiState.value.copy(analytics = analytics, analyticsLoading = false, analyticsError = null) }
                .onFailure { error -> _uiState.value = _uiState.value.copy(analyticsLoading = false, analyticsError = error.message ?: error::class.java.simpleName) }
        }
    }

    fun setAnalyticsFilters(filters: AnalyticsFilters) {
        val current = _uiState.value
        if (current.analyticsFilters == filters || current.selectedAccountKey == null) return
        _uiState.value = current.copy(analyticsFilters = filters, analytics = null, analyticsLoading = true, analyticsError = null)
        loadAnalytics(force = true)
    }

    fun eventPager(accountKey: String, buySellOnly: Boolean, hideRoutine: Boolean, eventName: String?): Flow<PagingData<MonitorEvent>> {
        _logTotalMatching.value = 0
        return Pager(
            config = PagingConfig(pageSize = 75, initialLoadSize = 75, prefetchDistance = 20, maxSize = 500, enablePlaceholders = false),
            pagingSourceFactory = { EventsPagingSource(repository, accountKey, buySellOnly, hideRoutine, eventName) { total -> _logTotalMatching.value = total } },
        ).flow
    }

    private fun applyAccountSelection(accountKey: String) {
        preferences.edit().putString(PREF_SELECTED_ACCOUNT, accountKey).apply()
        _uiState.value = _uiState.value.copy(
            loading = true,
            selectedAccountKey = accountKey,
            response = null,
            analytics = null,
            analyticsFilters = AnalyticsFilters(),
            analyticsError = null,
            error = null,
        )
        viewModelScope.launch { load(manual = true, forceAccounts = false) }
    }

    private fun startClock() {
        clockJob?.cancel()
        clockJob = viewModelScope.launch {
            while (true) {
                val now = System.currentTimeMillis()
                _uiState.value = _uiState.value.copy(nowEpochMs = now)
                checkForegroundStaleness(now)
                delay(1_000L)
            }
        }
    }

    private fun checkForegroundStaleness(now: Long) {
        val state = _uiState.value
        if (state.authStatus != AuthStatus.PAIRED) return
        if (isWeekend(now)) {
            staleNotificationShown = false
            NotificationHelper.cancelApiStale(getApplication<Application>())
            return
        }
        val connection = state.response?.snapshot?.connection
        if (connection != null) {
            if (connection.heartbeatStatus.equals("RUNNING", true) || connection.heartbeatStatus.equals("WEEKEND IDLE", true)) {
                staleNotificationShown = false
                NotificationHelper.cancelApiStale(getApplication<Application>())
                return
            }
            val seconds = (connection.lastUpdateAgeSeconds ?: 0.0).toLong()
            if (connection.heartbeatStatus.equals("STALE", true) && seconds >= BuildConfig.API_STALE_SECONDS && !staleNotificationShown) {
                staleNotificationShown = true
                NotificationHelper.showApiStale(getApplication<Application>(), seconds)
            }
            return
        }
        val reference = state.lastSuccessfulFetchEpochMs.takeIf { it > 0L } ?: statusMonitoringStartedMs
        val seconds = (now - reference).coerceAtLeast(0L) / 1000L
        if (seconds >= BuildConfig.API_STALE_SECONDS && !staleNotificationShown) {
            staleNotificationShown = true
            NotificationHelper.showApiStale(getApplication<Application>(), seconds)
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
        try {
            accounts = loadAccountsIfNeeded(previous.accounts, forceAccounts)
            require(accounts.isNotEmpty()) { "No permitted monitor accounts are configured for this device" }
            selectedKey = resolveSelectedAccount(accounts, previous.selectedAccountKey)
            _uiState.value = _uiState.value.copy(accountsLoading = false, accounts = accounts, selectedAccountKey = selectedKey)
            val response = repository.refresh(selectedKey)
            val now = System.currentTimeMillis()
            if (response.snapshot.connection.heartbeatStatus.equals("RUNNING", true) || response.snapshot.connection.heartbeatStatus.equals("WEEKEND IDLE", true)) {
                staleNotificationShown = false
                NotificationHelper.cancelApiStale(getApplication<Application>())
            }
            preferences.edit().putLong(PREF_BACKGROUND_LAST_SUCCESS, now).apply()
            _uiState.value = _uiState.value.copy(
                loading = false,
                refreshing = false,
                accountsLoading = false,
                accounts = accounts,
                selectedAccountKey = selectedKey,
                response = response,
                lastSuccessfulFetchEpochMs = now,
                nowEpochMs = now,
                error = null,
            )
        } catch (error: Throwable) {
            if (error is AuthenticationRequiredException) {
                pollingJob?.cancel()
                repository.clearSession()
                _uiState.value = UiState(authStatus = AuthStatus.UNPAIRED, loading = false, accountsLoading = false, deviceName = defaultDeviceName(), pairingError = error.message)
            } else {
                _uiState.value = _uiState.value.copy(
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

    private fun registerPushToken() {
        if (FirebaseApp.getApps(getApplication<Application>()).isEmpty()) return
        FirebaseMessaging.getInstance().token.addOnSuccessListener { token ->
            viewModelScope.launch { runCatching { repository.registerPushToken(token) } }
        }
    }


    private fun isWeekend(nowEpochMs: Long): Boolean {
        val day = Instant.ofEpochMilli(nowEpochMs).atZone(ZoneId.of("Europe/Warsaw")).dayOfWeek
        return day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY
    }

    private fun defaultDeviceName(): String = listOf(Build.MANUFACTURER, Build.MODEL).map { it.trim() }.filter { it.isNotBlank() }.distinct().joinToString(" ").ifBlank { "Android device" }

    override fun onCleared() {
        pollingJob?.cancel()
        clockJob?.cancel()
        super.onCleared()
    }

    companion object {
        private const val PREFERENCES = "oppw_monitor"
        private const val PREF_SELECTED_ACCOUNT = "selected_account"
        private const val PREF_BACKGROUND_LAST_SUCCESS = "background_last_success_ms"
        private const val ACCOUNTS_REFRESH_MS = 60_000L
    }
}

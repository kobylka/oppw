package com.oppw.monitor.notifications

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.oppw.monitor.BuildConfig
import com.oppw.monitor.data.StatusRepository
import java.util.concurrent.TimeUnit

class StaleStatusWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val repository = StatusRepository(applicationContext)
        if (!repository.hasSession()) return Result.success()
        val preferences = applicationContext.getSharedPreferences("oppw_monitor", Context.MODE_PRIVATE)
        val account = preferences.getString("selected_account", null) ?: return Result.success()
        val selectedIsReal = preferences.getBoolean("selected_account_is_real", false) || runCatching {
            repository.accounts().firstOrNull { it.key == account }?.isReal == true
        }.getOrDefault(false)
        if (selectedIsReal) return Result.success()
        return runCatching {
            repository.refresh(account)
            NotificationHelper.cancelApiStale(applicationContext)
            preferences.edit().putLong("background_last_success_ms", System.currentTimeMillis()).apply()
            Result.success()
        }.getOrElse {
            val last = preferences.getLong("background_last_success_ms", 0L)
            val seconds = if (last > 0) (System.currentTimeMillis() - last) / 1000 else BuildConfig.API_STALE_SECONDS
            if (seconds >= BuildConfig.API_STALE_SECONDS) NotificationHelper.showApiStale(applicationContext, seconds)
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "oppw-api-stale-check"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<StaleStatusWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(UNIQUE_NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
        }
    }
}

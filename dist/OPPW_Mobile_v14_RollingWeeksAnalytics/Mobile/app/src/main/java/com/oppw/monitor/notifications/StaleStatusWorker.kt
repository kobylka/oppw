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
import java.time.DayOfWeek
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.concurrent.TimeUnit

class StaleStatusWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val repository = StatusRepository(applicationContext)
        if (!repository.hasSession()) return Result.success()
        val day = ZonedDateTime.now(ZoneId.of("Europe/Warsaw")).dayOfWeek
        if (day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY) {
            NotificationHelper.cancelApiStale(applicationContext)
            return Result.success()
        }
        val preferences = applicationContext.getSharedPreferences("oppw_monitor", Context.MODE_PRIVATE)
        val account = preferences.getString("selected_account", null) ?: return Result.success()
        return runCatching {
            val response = repository.refresh(account)
            val connection = response.snapshot.connection
            val age = (connection.lastUpdateAgeSeconds ?: 0.0).toLong()
            if (connection.heartbeatStatus.equals("STALE", true) && age >= BuildConfig.API_STALE_SECONDS) NotificationHelper.showApiStale(applicationContext, age)
            else NotificationHelper.cancelApiStale(applicationContext)
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

package com.oppw.monitor.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.oppw.monitor.MainActivity
import com.oppw.monitor.R

object NotificationHelper {
    const val CRITICAL_CHANNEL = "oppw_critical"
    const val TRADE_CHANNEL = "oppw_trade"
    const val SYSTEM_CHANNEL = "oppw_system"

    fun createChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannels(
            listOf(
                NotificationChannel(CRITICAL_CHANNEL, "Critical OPPW alerts", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Protection, disconnection and stale strategy-heartbeat alerts"
                    enableVibration(true)
                },
                NotificationChannel(TRADE_CHANNEL, "Trade events", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Position opened and closed alerts"
                    enableVibration(true)
                },
                NotificationChannel(SYSTEM_CHANNEL, "Monitor status", NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description = "General monitor status notifications"
                },
            )
        )
    }

    fun show(context: Context, title: String, body: String, channel: String = CRITICAL_CHANNEL, id: Int = (title + body).hashCode()) {
        createChannels(context)
        val intent = Intent(context, MainActivity::class.java).apply { flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP }
        val pendingIntent = PendingIntent.getActivity(context, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        runCatching { NotificationManagerCompat.from(context).notify(id, notification) }
    }

    fun cancelApiStale(context: Context) = NotificationManagerCompat.from(context).cancel(7001)

    fun showApiStale(context: Context, seconds: Long) = show(
        context,
        "OPPW strategy heartbeat is stale",
        "The continuous MT5 loop has not updated the backend for ${seconds}s.",
        CRITICAL_CHANNEL,
        7001,
    )
}

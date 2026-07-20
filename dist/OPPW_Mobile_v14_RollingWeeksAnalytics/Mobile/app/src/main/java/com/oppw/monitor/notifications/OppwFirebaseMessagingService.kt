package com.oppw.monitor.notifications

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.oppw.monitor.data.StatusRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class OppwFirebaseMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        scope.launch { runCatching { StatusRepository(applicationContext).registerPushToken(token) } }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: message.data["title"] ?: "OPPW Monitor"
        val body = message.notification?.body ?: message.data["body"] ?: "Critical monitor event"
        val type = message.data["type"].orEmpty()
        val channel = if (type == "POSITION_OPENED" || type == "POSITION_CLOSED") NotificationHelper.TRADE_CHANNEL else NotificationHelper.CRITICAL_CHANNEL
        NotificationHelper.show(this, title, body, channel)
    }
}

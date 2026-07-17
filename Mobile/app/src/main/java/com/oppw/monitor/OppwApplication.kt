package com.oppw.monitor

import android.app.Application
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.oppw.monitor.notifications.NotificationHelper

class OppwApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        initializeFirebaseIfConfigured()
        NotificationHelper.createChannels(this)
    }

    private fun initializeFirebaseIfConfigured() {
        if (FirebaseApp.getApps(this).isNotEmpty()) return
        val values = listOf(BuildConfig.FIREBASE_APPLICATION_ID, BuildConfig.FIREBASE_PROJECT_ID, BuildConfig.FIREBASE_API_KEY, BuildConfig.FIREBASE_SENDER_ID)
        if (values.any { it.isBlank() }) return
        val options = FirebaseOptions.Builder()
            .setApplicationId(BuildConfig.FIREBASE_APPLICATION_ID)
            .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
            .setApiKey(BuildConfig.FIREBASE_API_KEY)
            .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
            .build()
        FirebaseApp.initializeApp(this, options)
    }
}

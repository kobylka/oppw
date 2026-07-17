package com.oppw.monitor

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.oppw.monitor.notifications.NotificationHelper
import com.oppw.monitor.notifications.StaleStatusWorker
import com.oppw.monitor.ui.MainViewModel
import com.oppw.monitor.ui.OppwMonitorApp
import com.oppw.monitor.ui.theme.OppwTheme

class MainActivity : FragmentActivity() {
    private val monitorViewModel: MainViewModel by viewModels()
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotificationHelper.createChannels(this)
        StaleStatusWorker.schedule(this)
        requestNotificationPermission()
        enableEdgeToEdge()
        setContent {
            OppwTheme { OppwMonitorApp(monitorViewModel) }
        }
    }

    override fun onStart() {
        super.onStart()
        monitorViewModel.onAppForegrounded()
    }

    override fun onStop() {
        monitorViewModel.onAppBackgrounded()
        super.onStop()
    }


    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}

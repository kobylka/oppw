package com.oppw.monitor

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.oppw.monitor.ui.MainViewModel
import com.oppw.monitor.ui.OppwMonitorApp
import com.oppw.monitor.ui.theme.OppwTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            OppwTheme {
                val viewModel: MainViewModel = viewModel()
                OppwMonitorApp(viewModel)
            }
        }
    }
}

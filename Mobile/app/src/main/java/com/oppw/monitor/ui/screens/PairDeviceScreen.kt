package com.oppw.monitor.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.PhoneAndroid
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.AuthStatus
import com.oppw.monitor.data.UiState
import com.oppw.monitor.ui.theme.CardBackground
import com.oppw.monitor.ui.theme.CardBorder
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary

@Composable
fun PairDeviceScreen(state: UiState, onPair: (String, String) -> Unit) {
    var code by rememberSaveable { mutableStateOf("") }
    var deviceName by rememberSaveable(state.deviceName) { mutableStateOf(state.deviceName) }
    val pairing = state.authStatus == AuthStatus.PAIRING
    val submit = { if (!pairing && code.filter { it.isLetterOrDigit() }.length >= 8) onPair(code, deviceName) }

    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = CardBackground,
            shape = MaterialTheme.shapes.large,
            border = androidx.compose.foundation.BorderStroke(1.dp, CardBorder),
        ) {
            Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Outlined.Lock, contentDescription = null, tint = PrimaryBlue)
                    Column {
                        Text("Pair this device", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text("Enter a one-time code created on the API server.", color = TextSecondary)
                    }
                }

                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.uppercase().take(19) },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Pairing code") },
                    placeholder = { Text("ABCD-EFGH-JKLM") },
                    singleLine = true,
                    enabled = !pairing,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, imeAction = ImeAction.Next),
                )

                OutlinedTextField(
                    value = deviceName,
                    onValueChange = { deviceName = it.take(100) },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Device name") },
                    leadingIcon = { Icon(Icons.Outlined.PhoneAndroid, contentDescription = null) },
                    singleLine = true,
                    enabled = !pairing,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                )

                state.pairingError?.let { Text(it, color = MaterialTheme.colorScheme.error) }

                Button(
                    onClick = submit,
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !pairing && code.filter { it.isLetterOrDigit() }.length >= 8 && deviceName.isNotBlank(),
                ) {
                    if (pairing) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(12.dp))
                        Text("Pairing…")
                    } else {
                        Text("Pair device")
                    }
                }

                Text(
                    "The app receives read-only access to the accounts assigned to this code. MySQL, MT5, and publisher credentials are never stored on the phone.",
                    color = TextSecondary,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

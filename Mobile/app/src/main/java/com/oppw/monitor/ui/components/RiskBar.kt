package com.oppw.monitor.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.price
import kotlin.math.max
import kotlin.math.min

@Composable
fun RiskBar(stopLoss: Double, entry: Double, current: Double) {
    if (stopLoss <= 0 || entry <= 0 || current <= 0) return
    val low = min(stopLoss, min(entry, current))
    val high = max(stopLoss, max(entry, current))
    val range = (high - low).takeIf { it > 0 } ?: 1.0
    val entryFraction = ((entry - low) / range).toFloat().coerceIn(0f, 1f)
    val currentFraction = ((current - low) / range).toFloat().coerceIn(0f, 1f)

    Column {
        Box(
            Modifier.fillMaxWidth().height(14.dp).background(
                Brush.horizontalGradient(listOf(DangerRed, BrightGreen)), RoundedCornerShape(50)
            )
        ) {
            Box(Modifier.offset(x = (entryFraction * 280).dp).background(androidx.compose.ui.graphics.Color.White).height(14.dp).padding(horizontal = 2.dp))
            Box(Modifier.offset(x = (currentFraction * 280).dp).background(androidx.compose.ui.graphics.Color(0xFF3B91FF)).height(14.dp).padding(horizontal = 2.dp))
        }
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween) {
            Text("SL ${price(stopLoss)}", color = DangerRed, fontSize = 11.sp)
            Text("Entry ${price(entry)}", color = TextSecondary, fontSize = 11.sp)
            Text("Price ${price(current)}", color = BrightGreen, fontSize = 11.sp)
        }
    }
}

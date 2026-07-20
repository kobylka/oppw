package com.oppw.monitor.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.DangerRed
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.price

private data class PriceMarker(val label: String, val value: Double, val color: Color)

@Composable
fun RiskBar(stopLoss: Double, entry: Double, current: Double) {
    if (stopLoss <= 0 || entry <= 0 || current <= 0) return
    val markers = listOf(
        PriceMarker("SL", stopLoss, DangerRed),
        PriceMarker("Entry", entry, TextSecondary),
        PriceMarker("Price", current, PrimaryBlue),
    ).sortedBy { it.value }
    val low = markers.first().value
    val high = markers.last().value
    val range = (high - low).takeIf { it > 0 } ?: 1.0

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            Box(
                Modifier.fillMaxWidth().height(14.dp).background(
                    Brush.horizontalGradient(listOf(DangerRed, BrightGreen)), RoundedCornerShape(50)
                )
            )
            markers.forEach { marker ->
                val fraction = ((marker.value - low) / range).toFloat().coerceIn(0f, 1f)
                Box(
                    Modifier.offset(x = (maxWidth - 3.dp) * fraction)
                        .width(3.dp)
                        .height(14.dp)
                        .background(marker.color)
                )
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            markers.forEach { marker ->
                Text("${marker.label} ${price(marker.value)}", color = marker.color, fontSize = 11.sp, modifier = Modifier.padding(horizontal = 2.dp))
            }
        }
    }
}

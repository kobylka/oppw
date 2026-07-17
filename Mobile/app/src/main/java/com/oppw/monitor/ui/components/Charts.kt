package com.oppw.monitor.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.EquityPoint
import com.oppw.monitor.ui.theme.CardBorder
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.money

@Composable
fun Sparkline(values: List<Double>, modifier: Modifier = Modifier) {
    Canvas(modifier.fillMaxWidth().height(130.dp)) {
        if (values.size < 2) return@Canvas
        val min = values.minOrNull() ?: return@Canvas
        val max = values.maxOrNull() ?: return@Canvas
        val range = (max - min).takeIf { it > 0 } ?: 1.0

        repeat(4) { index ->
            val y = size.height * index / 3f
            drawLine(CardBorder, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
        }

        val path = Path()
        values.forEachIndexed { index, value ->
            val x = size.width * index / values.lastIndex.coerceAtLeast(1).toFloat()
            val y = size.height - ((value - min) / range * size.height).toFloat()
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, PrimaryBlue, style = Stroke(width = 5f, cap = StrokeCap.Round))
    }
}

@Composable
fun EquityChart(points: List<EquityPoint>, currency: String, modifier: Modifier = Modifier) {
    if (points.size < 2) {
        Text("Not enough history yet", color = TextSecondary)
        return
    }
    val values = points.map { it.value }
    val start = values.first()
    val end = values.last()
    val min = values.minOrNull() ?: start
    val max = values.maxOrNull() ?: start
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(money(start, currency), color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            Text(money(end, currency), style = MaterialTheme.typography.labelMedium)
        }
        Sparkline(values)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Low ${money(min, currency)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
            Text("High ${money(max, currency)}", color = TextSecondary, style = MaterialTheme.typography.labelMedium)
        }
    }
}

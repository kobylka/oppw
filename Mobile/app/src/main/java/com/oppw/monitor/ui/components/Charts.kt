package com.oppw.monitor.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.oppw.monitor.data.EquityPoint
import com.oppw.monitor.ui.theme.BrightGreen
import com.oppw.monitor.ui.theme.CardBorder
import com.oppw.monitor.ui.theme.PrimaryBlue
import com.oppw.monitor.ui.theme.TextSecondary
import com.oppw.monitor.util.dateOnly
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

@Composable
fun AllTimeEquityChart(points: List<EquityPoint>, currency: String, initialBalance: Double, modifier: Modifier = Modifier) {
    if (points.isEmpty()) {
        Text("No all-time history yet", color = TextSecondary)
        return
    }
    val firstExplicitDeposit = points.firstNotNullOfOrNull { point -> point.deposits?.takeIf { it > 0.0 } }
    var carriedDeposits = firstExplicitDeposit ?: initialBalance.takeIf { it > 0.0 } ?: points.first().value.coerceAtLeast(0.0)
    val normalizedDeposits = points.map { point ->
        val explicit = point.deposits
        if (explicit != null && explicit > 0.0) carriedDeposits = explicit
        carriedDeposits
    }
    val allValues = points.map { it.value } + normalizedDeposits
    val min = allValues.minOrNull() ?: 0.0
    val max = allValues.maxOrNull() ?: 1.0
    val range = (max - min).takeIf { it > 0 } ?: 1.0
    val middle = points[points.lastIndex / 2]

    Column(modifier, verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            ChartLegend("Equity", PrimaryBlue)
            ChartLegend("Deposits to date", BrightGreen)
        }
        Canvas(Modifier.fillMaxWidth().height(170.dp)) {
            repeat(4) { index ->
                val y = size.height * index / 3f
                drawLine(CardBorder, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
            }

            fun pathFor(values: List<Double>, stepped: Boolean = false): Path {
                val path = Path()
                var previousY: Float? = null
                values.forEachIndexed { index, value ->
                    val x = if (values.size == 1) size.width / 2f else size.width * index / values.lastIndex.toFloat()
                    val y = size.height - ((value - min) / range * size.height).toFloat()
                    if (previousY == null) path.moveTo(x, y)
                    else if (stepped) {
                        path.lineTo(x, previousY!!)
                        path.lineTo(x, y)
                    } else path.lineTo(x, y)
                    previousY = y
                }
                return path
            }

            drawPath(pathFor(points.map { it.value }), PrimaryBlue, style = Stroke(width = 5f, cap = StrokeCap.Round))
            drawPath(
                pathFor(normalizedDeposits, stepped = true),
                BrightGreen,
                style = Stroke(width = 4f, cap = StrokeCap.Round, pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f))),
            )
            if (points.size == 1) {
                val equityY = size.height - ((points.first().value - min) / range * size.height).toFloat()
                val depositsY = size.height - ((normalizedDeposits.first() - min) / range * size.height).toFloat()
                drawCircle(PrimaryBlue, radius = 6f, center = Offset(size.width / 2f, equityY))
                drawCircle(BrightGreen, radius = 5f, center = Offset(size.width / 2f, depositsY))
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(dateOnly(points.first().time), color = TextSecondary, style = MaterialTheme.typography.labelSmall)
            Text(dateOnly(middle.time), color = TextSecondary, style = MaterialTheme.typography.labelSmall)
            Text(dateOnly(points.last().time), color = TextSecondary, style = MaterialTheme.typography.labelSmall)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Equity ${money(points.last().value, currency)}", style = MaterialTheme.typography.labelMedium)
            Text("Deposits ${money(normalizedDeposits.last(), currency)}", color = BrightGreen, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun ChartLegend(label: String, color: Color) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Canvas(Modifier.size(9.dp)) { drawCircle(color) }
        Text(label, color = TextSecondary, style = MaterialTheme.typography.labelMedium)
    }
}

package com.oppw.monitor.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Colors = darkColorScheme(
    primary = PrimaryBlue,
    secondary = BrightGreen,
    tertiary = WarningAmber,
    background = AppBackground,
    surface = CardBackground,
    surfaceVariant = Color(0xFF102238),
    onPrimary = Color.White,
    onSecondary = Color.Black,
    onBackground = TextPrimary,
    onSurface = TextPrimary,
    error = DangerRed,
)

@Composable
fun OppwTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Colors, typography = AppTypography, content = content)
}

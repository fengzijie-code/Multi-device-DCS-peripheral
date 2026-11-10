package com.fengzijie.dcsperipheral.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** 全局配色。夜间座舱环境用纯暗色，避免屏幕反光影响仪表判读。 */
object Ink {
    val Bg = Color(0xFF0D1117)
    val Surface = Color(0xFF161B22)
    val Line = Color(0xFF2A3038)
    val Fg = Color(0xFFE6EDF3)
    val Dim = Color(0xFF8B949E)
    val Teal = Color(0xFF3FB950)
    val Amber = Color(0xFFD29922)
    val Red = Color(0xFFF85149)
    val Sky = Color(0xFF14395C)
    val Ground = Color(0xFF5B3F1E)
}

private val DarkColors = darkColorScheme(
    primary = Ink.Teal,
    onPrimary = Color(0xFF06120A),
    background = Ink.Bg,
    onBackground = Ink.Fg,
    surface = Ink.Surface,
    onSurface = Ink.Fg,
    surfaceVariant = Color(0xFF1B2130),
    onSurfaceVariant = Ink.Dim,
    outline = Ink.Line,
    error = Ink.Red,
)

@Composable
fun DcsTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = DarkColors, content = content)
}

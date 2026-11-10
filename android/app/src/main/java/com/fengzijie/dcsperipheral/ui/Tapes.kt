package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.roundToLong

/**
 * 垂直滚动刻度带。
 *
 * 为什么不用「数字窗」：数字只告诉你当前值，刻度带告诉你**当前值在量程里的位置**。
 * 爬升时扫一眼就知道自己是 8000 还是差 200 到底，数字得先读再算。
 *
 * @param range     中心线上下各显示多少个单位
 * @param minorStep 最小刻度间隔（决定刻度密度）
 * @param labelStep 标数字的间隔，应为 minorStep 的整数倍
 */
@Composable
fun VerticalTape(
    value: Double,
    range: Double,
    minorStep: Double,
    labelStep: Double,
    modifier: Modifier = Modifier,
    unit: String = "",
    decimals: Int = 0,
    alignEnd: Boolean = true,
    accent: Color = Ink.Fg,
    valueColor: Color = Ink.Teal,
) {
    val measurer = rememberTextMeasurer()
    val tickStyle = TextStyle(
        color = Ink.Dim,
        fontSize = 10.sp,
        fontFamily = FontFamily.Monospace,
    )
    val valueStyle = TextStyle(
        color = valueColor,
        fontSize = 17.sp,
        fontWeight = FontWeight.Medium,
        fontFamily = FontFamily.Monospace,
    )
    val unitStyle = TextStyle(color = Ink.Dim, fontSize = 9.sp, fontFamily = FontFamily.Monospace)

    Canvas(modifier) {
        val w = size.width
        val h = size.height
        if (w <= 0f || h <= 0f || range <= 0 || minorStep <= 0) return@Canvas

        val cx = w / 2f
        val cy = h / 2f
        val pxPerUnit = (h / 2f) / range
        val corner = 8f * density
        val panel = Path().apply { addRoundRect(RoundRect(0f, 0f, w, h, corner, corner)) }

        drawPath(panel, Ink.Surface)
        drawPath(panel, Ink.Line, style = Stroke(width = 1f * density))

        clipPath(panel) {
            // 刻度：从 value-range 到 value+range 之间所有 minorStep 的整数倍
            val lo = floor((value - range) / minorStep) * minorStep
            val hi = value + range
            var v = lo
            var guard = 0
            while (v <= hi && guard < 400) {
                guard++
                val y = cy + (((value - v) / range).toFloat() * (h / 2f))
                val isMajor = abs(v / labelStep - (v / labelStep).roundToLong()) < 1e-6
                val tickLen = if (isMajor) w * 0.42f else w * 0.22f
                val start = if (alignEnd) w - 6f * density - tickLen else 6f * density
                drawLine(
                    color = if (isMajor) Ink.Fg else Ink.Dim,
                    start = Offset(start, y),
                    end = Offset(start + tickLen, y),
                    strokeWidth = (if (isMajor) 1.4f else 1f) * density,
                )
                if (isMajor) {
                    val label = fmtTape(v, decimals)
                    val layout = measurer.measure(label, tickStyle)
                    val tx = if (alignEnd) {
                        start - 5f * density - layout.size.width
                    } else {
                        start + tickLen + 5f * density
                    }
                    drawText(layout, topLeft = Offset(tx, y - layout.size.height / 2f))
                }
                v += minorStep
            }
            // 顶部/底部轻微渐隐，暗示还可以继续滚。
            // 只压两端很窄的一段：压太宽会把刻度和数字一起吃掉。
            drawRect(
                brush = androidx.compose.ui.graphics.Brush.verticalGradient(
                    0f to Ink.Surface, 0.07f to Color.Transparent,
                    0.93f to Color.Transparent, 1f to Ink.Surface,
                ),
                size = Size(w, h),
            )
        }

        // 单位做成顶部的固定标签，不放进值窗。
        // 放进值窗的话，「4576 ft」在 80dp 宽的带子里塞不下，会溢出边框。
        // 必须画在 clipPath 之后：否则会被顶部那段渐隐盖住，看起来像被裁掉了。
        if (unit.isNotEmpty()) {
            val ul = measurer.measure(unit, unitStyle)
            drawRect(
                color = Ink.Surface,
                topLeft = Offset(0f, 0f),
                size = Size(w, ul.size.height + 4f * density),
            )
            drawText(ul, topLeft = Offset(cx - ul.size.width / 2f, 2f * density))
        }

        // 当前值窗：贴在读数一侧，带一个指向刻度带的三角。
        // 宽度只占 72%：再宽就把上下相邻的刻度全遮住了，刻度带就失去意义了。
        val boxW = w * 0.72f
        val boxH = 28f * density
        val boxX = cx - boxW / 2f
        val boxY = cy - boxH / 2f
        drawRoundRect(
            color = Color(0xE60D1117),
            topLeft = Offset(boxX, boxY),
            size = Size(boxW, boxH),
            cornerRadius = CornerRadius(5f * density, 5f * density),
        )
        drawRoundRect(
            color = valueColor.copy(alpha = 0.55f),
            topLeft = Offset(boxX, boxY),
            size = Size(boxW, boxH),
            cornerRadius = CornerRadius(5f * density, 5f * density),
            style = Stroke(width = 1.2f * density),
        )

        val text = fmtTape(value, decimals)
        val layout = measurer.measure(text, valueStyle)
        drawText(
            layout,
            topLeft = Offset(cx - layout.size.width / 2f, cy - layout.size.height / 2f),
        )

        // 指向刻度带的三角（alignEnd 时朝右）
        val tri = 6f * density
        val triPath = Path().apply {
            if (alignEnd) {
                moveTo(boxX + boxW, cy - tri)
                lineTo(boxX + boxW + tri, cy)
                lineTo(boxX + boxW, cy + tri)
            } else {
                moveTo(boxX, cy - tri)
                lineTo(boxX - tri, cy)
                lineTo(boxX, cy + tri)
            }
            close()
        }
        drawPath(triPath, valueColor)
    }
}

private fun fmtTape(v: Double, decimals: Int): String {
    if (!v.isFinite()) return "--"
    return if (decimals <= 0) v.roundToLong().toString()
    else String.format(java.util.Locale.US, "%.${decimals}f", v)
}

/**
 * 水平航向带。0–360 环绕，所以每个刻度的位置要算「最短角差」，
 * 否则从 359 转到 001 时整条带子会横跳一圈。
 */
@Composable
fun HeadingTape(
    headingDeg: Double,
    modifier: Modifier = Modifier,
    range: Double = 50.0,
    minorStep: Double = 5.0,
    labelStep: Double = 30.0,
) {
    val measurer: TextMeasurer = rememberTextMeasurer()
    val style = TextStyle(color = Ink.Dim, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
    val nowStyle = TextStyle(
        color = Ink.Teal, fontSize = 15.sp,
        fontWeight = FontWeight.Medium, fontFamily = FontFamily.Monospace,
    )

    Canvas(modifier) {
        val w = size.width
        val h = size.height
        if (w <= 0f || h <= 0f) return@Canvas

        val cx = w / 2f
        val pxPerDeg = (w / 2f) / range

        drawRect(Ink.Surface, size = Size(w, h))
        drawLine(Ink.Line, Offset(0f, h), Offset(w, h), 1f * density)

        val hdg = ((headingDeg % 360) + 360) % 360
        var a = 0.0
        while (a < 360.0) {
            val delta = shortestDelta(a - hdg)
            if (abs(delta) <= range) {
                val x = cx + ((delta / range).toFloat() * (w / 2f))
                val isMajor = abs(a % labelStep) < 1e-6
                val len = if (isMajor) h * 0.42f else h * 0.22f
                drawLine(
                    color = if (isMajor) Ink.Fg else Ink.Dim,
                    start = Offset(x, h),
                    end = Offset(x, h - len),
                    strokeWidth = (if (isMajor) 1.4f else 1f) * density,
                )
                if (isMajor) {
                    val label = ((a.toInt() % 360) + 360) % 360
                    val txt = when (label) {
                        0 -> "N"
                        90 -> "E"
                        180 -> "S"
                        270 -> "W"
                        else -> "%03d".format(label)
                    }
                    val layout = measurer.measure(txt, style)
                    drawText(layout, topLeft = Offset(x - layout.size.width / 2f, h * 0.06f))
                }
            }
            a += minorStep
        }

        // 中心指针 + 当前值
        drawLine(Ink.Teal, Offset(cx, h), Offset(cx, h - h * 0.55f), 2f * density)
        val tri = 5f * density
        val p = Path().apply {
            moveTo(cx - tri, h - h * 0.55f)
            lineTo(cx + tri, h - h * 0.55f)
            lineTo(cx, h - h * 0.55f + tri)
            close()
        }
        drawPath(p, Ink.Teal)

        val txt = "%03d".format(((hdg.roundToLong() % 360) + 360) % 360)
        val layout = measurer.measure(txt, nowStyle)
        drawRoundRect(
            color = Color(0xE60D1117),
            topLeft = Offset(cx - layout.size.width / 2f - 6f * density, h * 0.34f),
            size = Size(layout.size.width + 12f * density, layout.size.height + 2f * density),
            cornerRadius = CornerRadius(4f * density, 4f * density),
        )
        drawText(layout, topLeft = Offset(cx - layout.size.width / 2f, h * 0.36f))
    }
}

/** 返回 (-180, 180] 区间内的最短角差，处理 359→001 的环绕。 */
private fun shortestDelta(d: Double): Double {
    var x = d % 360.0
    if (x > 180.0) x -= 360.0
    if (x < -180.0) x += 360.0
    return x
}

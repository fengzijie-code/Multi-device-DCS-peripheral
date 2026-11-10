package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import kotlin.math.abs

/**
 * 姿态仪（人工地平仪）。
 *
 * P0 里它的作用不只是「好看」：它是唯一能一眼看出**数据是否真的在动、
 * 且方向对不对**的组件。数字可以伪造，地平线跟着滚转倾斜这一点很难骗人。
 *
 * 形状选矩形而不是圆形：手机是 20:9 长屏，圆形只能取宽度，上下会各留出
 * 几百像素的死区；矩形能填满可用空间，观感也更接近真实 MFD。
 *
 * 单位约定：入参是弧度（与 DCS 的 LoGetSelfData 一致），内部转成度绘制。
 */
@Composable
fun AttitudeIndicator(
    pitchRad: Double,
    bankRad: Double,
    modifier: Modifier = Modifier,
) {
    val pitchDeg = Math.toDegrees(pitchRad).toFloat().coerceIn(-30f, 30f)
    val bankDeg = Math.toDegrees(bankRad).toFloat()

    Canvas(modifier) {
        val w = size.width
        val h = size.height
        if (w <= 0f || h <= 0f) return@Canvas

        val cx = w / 2f
        val cy = h / 2f
        val corner = 14f * density
        val frame = Path().apply {
            addRoundRect(RoundRect(0f, 0f, w, h, corner, corner))
        }
        // 竖直方向上下各 30°，正好铺满
        val pxPerDeg = h / 60f

        clipPath(frame) {
            rotate(degrees = -bankDeg, pivot = Offset(cx, cy)) {
                translate(top = pitchDeg * pxPerDeg) {
                    drawRect(
                        color = Ink.Sky,
                        topLeft = Offset(cx - w, cy - h * 1.5f),
                        size = Size(w * 2f, h * 1.5f),
                    )
                    drawRect(
                        color = Ink.Ground,
                        topLeft = Offset(cx - w, cy),
                        size = Size(w * 2f, h * 1.5f),
                    )
                    drawLine(
                        color = Ink.Fg,
                        start = Offset(cx - w, cy),
                        end = Offset(cx + w, cy),
                        strokeWidth = 2.6f * density,
                    )
                    // 俯仰梯：真实 ADI 的梯线是**中间断开的两段**，不是整条横线。
                    // 画成整条会横穿机翼符号，看起来像随手划的棍子。
                    val gap = w * 0.055f
                    for (dpts in -30..30 step 5) {
                        if (dpts == 0) continue
                        val y = cy - dpts * pxPerDeg
                        val half = if (dpts % 10 == 0) w * 0.085f else w * 0.05f
                        drawLine(
                            color = Ink.Dim,
                            start = Offset(cx - gap - half, y),
                            end = Offset(cx - gap, y),
                            strokeWidth = 1.3f * density,
                        )
                        drawLine(
                            color = Ink.Dim,
                            start = Offset(cx + gap, y),
                            end = Offset(cx + gap + half, y),
                            strokeWidth = 1.3f * density,
                        )
                    }
                }
            }
        }

        // 边框
        drawPath(path = frame, color = Ink.Line, style = Stroke(width = 1.5f * density))

        // 固定机翼符号（不随姿态转动）
        drawLine(
            color = Ink.Fg,
            start = Offset(cx - w * 0.20f, cy),
            end = Offset(cx - w * 0.06f, cy),
            strokeWidth = 3f * density,
        )
        drawLine(
            color = Ink.Fg,
            start = Offset(cx + w * 0.06f, cy),
            end = Offset(cx + w * 0.20f, cy),
            strokeWidth = 3f * density,
        )
        drawCircle(color = Ink.Fg, radius = 2.5f * density, center = Offset(cx, cy))

        // 顶部滚转带：固定参考刻度（0/±30/±60）+ 随滚转滑动的指针。
        // 只有滑动的小圆点而没有参考刻度时，看不出「偏了多少」，等于没画。
        val tapeY = 11f * density
        val span = w * 0.26f          // ±60° 对应的横向距离

        for (deg in intArrayOf(-60, -30, 0, 30, 60)) {
            val tx = cx + (deg / 60f) * span
            val long = deg == 0
            drawLine(
                color = if (long) Ink.Fg else Ink.Dim,
                start = Offset(tx, 0f),
                end = Offset(tx, if (long) tapeY * 1.6f else tapeY),
                strokeWidth = (if (long) 2f else 1.4f) * density,
            )
        }

        val bx = cx + (bankDeg.coerceIn(-60f, 60f) / 60f) * span
        val tickColor = when {
            abs(bankDeg) > 70f -> Ink.Red
            abs(bankDeg) > 45f -> Ink.Amber
            else -> Ink.Fg
        }
        val tip = Path().apply {
            moveTo(bx - 4f * density, tapeY * 0.9f)
            lineTo(bx + 4f * density, tapeY * 0.9f)
            lineTo(bx, tapeY * 1.9f)
            close()
        }
        drawPath(tip, tickColor)
    }
}

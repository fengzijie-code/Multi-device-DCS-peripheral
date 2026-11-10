package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material3.Text
import com.fengzijie.dcsperipheral.input.YokeSettings
import com.fengzijie.dcsperipheral.input.YokeState
import java.util.Locale
import kotlin.math.abs
import kotlin.math.min

private fun f1(v: Float): String = String.format(Locale.US, "%.1f", v)
private fun sgn2(v: Float): String = String.format(Locale.US, "%+.2f", v)

/**
 * 摇杆页。
 *
 * 布局思路：左边一块「杆位盘」占主要视觉面积，右边一排竖向的开关和步进。
 * 之所以不用滑块调参数：横屏可用高度只有 360dp 左右，三个 Material 滑块
 * 就要吃掉 150dp，而且手指在滑杆上很难精确停在 22°。步进按钮一格一个
 * 确定值，反而更快更准。
 */
@Composable
fun YokeScreen(
    st: YokeState,
    set: YokeSettings,
    onSettings: (YokeSettings) -> Unit,
    onToggleArm: () -> Unit,
    onCalibrate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier = modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1.05f).fillMaxHeight()) {
            DeflectionPad(
                st = st,
                rangeDeg = set.rangeDeg,
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )
            Spacer(Modifier.height(4.dp))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Readout("左右", sgn2(st.x), if (abs(st.x) > 0.01f) Ink.Fg else Ink.Dim)
                Readout("前后", sgn2(st.y), if (abs(st.y) > 0.01f) Ink.Fg else Ink.Dim)
                Readout("原始", "${f1(st.rollDeg)}/${f1(st.pitchDeg)}", Ink.Dim)
                Readout("链路", "${st.rttMs}ms ${f1(st.hz)}Hz", Ink.Dim)
            }
        }

        Column(
            Modifier
                .weight(1f)
                .fillMaxHeight()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            // 解锁键放最上面、最显眼：它是唯一能让飞机真的动的开关
            ArmButton(armed = st.armed, ready = st.ready, onClick = onToggleArm)

            // 操纵链有五跳（手机→桥接→vjoy_out→驱动→DCS），任一跳断了
            // 现象都是「杆不动」。这一行专门用来指出断在第几跳之后。
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(7.dp)
                        .background(if (st.vjoyOk) Ink.Teal else Ink.Amber, CircleShape)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    text = if (st.vjoyOk) "PC 端虚拟摇杆就绪"
                    else "PC 端虚拟摇杆未运行 · 杆不会动",
                    color = if (st.vjoyOk) Ink.Dim else Ink.Amber,
                    fontSize = 11.sp,
                )
            }

            st.notice?.let {
                Text(
                    text = it,
                    color = Ink.Amber,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(horizontal = 2.dp),
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Chip(
                    text = if (st.hasNeutral) "重新校零" else "校零",
                    on = !st.hasNeutral,
                    onClick = onCalibrate,
                    modifier = Modifier.weight(1f),
                )
                Chip(
                    text = if (set.swapAxes) "横握" else "竖握",
                    on = true,
                    onClick = { onSettings(set.copy(swapAxes = !set.swapAxes)) },
                    modifier = Modifier.weight(0.8f),
                )
            }

            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Chip(
                    text = if (set.invertX) "左右 翻转" else "左右 正常",
                    on = set.invertX,
                    onClick = { onSettings(set.copy(invertX = !set.invertX)) },
                    modifier = Modifier.weight(1f),
                )
                Chip(
                    text = if (set.invertY) "前后 翻转" else "前后 正常",
                    on = set.invertY,
                    onClick = { onSettings(set.copy(invertY = !set.invertY)) },
                    modifier = Modifier.weight(1f),
                )
            }

            Stepper(
                label = "行程",
                value = "${set.rangeDeg.toInt()}°",
                hint = "推满要倾斜多少度",
                onMinus = { onSettings(set.copy(rangeDeg = (set.rangeDeg - 1f).coerceAtLeast(8f))) },
                onPlus = { onSettings(set.copy(rangeDeg = (set.rangeDeg + 1f).coerceAtMost(45f))) },
            )
            Stepper(
                label = "死区",
                value = "${f1(set.deadbandDeg)}°",
                hint = "中位附近多大范围算没动",
                onMinus = { onSettings(set.copy(deadbandDeg = (set.deadbandDeg - 0.5f).coerceAtLeast(0f))) },
                onPlus = { onSettings(set.copy(deadbandDeg = (set.deadbandDeg + 0.5f).coerceAtMost(10f))) },
            )
            Stepper(
                label = "曲线",
                value = String.format(Locale.US, "%.2f", set.expo),
                hint = "大 = 中间更细，末端仍满",
                onMinus = { onSettings(set.copy(expo = (set.expo - 0.05f).coerceAtLeast(0f))) },
                onPlus = { onSettings(set.copy(expo = (set.expo + 0.05f).coerceAtMost(1f))) },
            )
        }
    }
}

@Composable
private fun Readout(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, color = Ink.Dim, fontSize = 9.sp)
        Text(
            value,
            color = color,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            softWrap = false,
        )
    }
}

@Composable
private fun ArmButton(armed: Boolean, ready: Boolean, onClick: () -> Unit) {
    val bg = when {
        armed -> Ink.Red.copy(alpha = 0.18f)
        ready -> Ink.Teal.copy(alpha = 0.14f)
        else -> Ink.Surface
    }
    val line = when {
        armed -> Ink.Red
        ready -> Ink.Teal
        else -> Ink.Line
    }
    val fg = when {
        armed -> Ink.Red
        ready -> Ink.Teal
        else -> Ink.Dim
    }
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(bg)
            .border(1.5.dp, line, RoundedCornerShape(10.dp))
            .clickable(enabled = ready) { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = when {
                armed -> "已解锁 · 点此上锁"
                ready -> "点击解锁（开始操纵）"
                else -> "先校零才能解锁"
            },
            color = fg,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun Chip(
    text: String,
    on: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(34.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Ink.Teal.copy(alpha = 0.18f) else Ink.Surface)
            .border(1.dp, if (on) Ink.Teal.copy(alpha = 0.7f) else Ink.Line, RoundedCornerShape(8.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = if (on) Ink.Teal else Ink.Dim,
            fontSize = 12.sp,
            maxLines = 1,
            softWrap = false,
        )
    }
}

/**
 * 参数调节行。
 *
 * 用步进按钮而不是 Material Slider，是因为横屏可用高度只有 300 多 dp，
 * 三个滑块要吃掉一半；而且手指在滑轨上很难精确停在 22°，步进一格一个
 * 确定值反而更快。
 *
 * 说明文字与数值放在**同一行**：竖排两行的写法在加上「虚拟摇杆就绪」
 * 那一行以后会把最后一个参数顶到折叠线以下，飞行中还要滚动才能调参数
 * 是不可接受的。
 */
@Composable
private fun Stepper(
    label: String,
    value: String,
    hint: String,
    onMinus: () -> Unit,
    onPlus: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(Ink.Surface)
            .padding(start = 8.dp, end = 4.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = Ink.Dim, fontSize = 11.sp, maxLines = 1, softWrap = false)
        Spacer(Modifier.width(6.dp))
        Text(
            value,
            color = Ink.Fg,
            fontSize = 12.sp,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            softWrap = false,
        )
        Spacer(Modifier.width(8.dp))
        Text(
            hint,
            color = Ink.Dim.copy(alpha = 0.6f),
            fontSize = 9.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        StepKey("−", onMinus)
        StepKey("+", onPlus)
    }
}

@Composable
private fun StepKey(text: String, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(28.dp)
            .clip(RoundedCornerShape(6.dp))
            .background(Ink.Line.copy(alpha = 0.55f))
            .clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = Ink.Fg, fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}

/**
 * 杆位盘：一个方框 + 十字线 + 一个代表杆位的圆点。
 *
 * 为什么值得单独画一块：光看数字很难判断「我到底推了多少」，
 * 而杆位和飞机的响应是强耦合的。有了这个盘，调死区和行程时
 * 能直接看到「手抖」有多大、离满杆还有多远。
 */
@Composable
private fun DeflectionPad(st: YokeState, rangeDeg: Float, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val side = min(size.width, size.height) * 0.94f
        val left = (size.width - side) / 2f
        val top = (size.height - side) / 2f
        val cx = left + side / 2f
        val cy = top + side / 2f
        val r = 10f

        // 底盘
        drawRoundRect(
            color = Ink.Surface,
            topLeft = Offset(left, top),
            size = Size(side, side),
            cornerRadius = CornerRadius(r, r),
        )
        drawRoundRect(
            color = Ink.Line,
            topLeft = Offset(left, top),
            size = Size(side, side),
            cornerRadius = CornerRadius(r, r),
            style = Stroke(width = 1.5f),
        )

        // 十字与半杆网格
        drawLine(Ink.Line, Offset(left, cy), Offset(left + side, cy), strokeWidth = 1f)
        drawLine(Ink.Line, Offset(cx, top), Offset(cx, top + side), strokeWidth = 1f)
        val half = side / 2f
        for (k in floatArrayOf(0.5f)) {
            val d = half * k
            drawLine(Ink.Line.copy(alpha = 0.45f), Offset(cx - d, top), Offset(cx - d, top + side), 1f)
            drawLine(Ink.Line.copy(alpha = 0.45f), Offset(cx + d, top), Offset(cx + d, top + side), 1f)
            drawLine(Ink.Line.copy(alpha = 0.45f), Offset(left, cy - d), Offset(left + side, cy - d), 1f)
            drawLine(Ink.Line.copy(alpha = 0.45f), Offset(left, cy + d), Offset(left + side, cy + d), 1f)
        }

        // 杆位点。用**原始角度**除以行程来定位，而不是用曲线后的输出值 ——
        // 曲线是给飞机看的，人调手感时需要看真实的物理倾斜。
        val span = rangeDeg.coerceAtLeast(1f)
        val dx = (st.rollDeg / span).coerceIn(-1f, 1f) * half
        val dy = -(st.pitchDeg / span).coerceIn(-1f, 1f) * half
        val dotColor = if (st.armed) Ink.Teal else Ink.Dim
        if (st.armed) {
            drawCircle(dotColor.copy(alpha = 0.16f), radius = 26f, center = Offset(cx + dx, cy + dy))
        }
        drawCircle(dotColor, radius = 9f, center = Offset(cx + dx, cy + dy))
        drawCircle(Color.Black.copy(alpha = 0.45f), radius = 9f, center = Offset(cx + dx, cy + dy), style = Stroke(1.5f))

        // 四个方向的字，帮助判断握法对不对
        // （不画文字，避免在 Canvas 里引 TextMeasurer；用短刻度代替）
        drawLine(Ink.Dim, Offset(cx - 3, top + 6f), Offset(cx + 3, top + 6f), 2f)
        drawLine(Ink.Dim, Offset(cx - 3, top + side - 6f), Offset(cx + 3, top + side - 6f), 2f)
        drawLine(Ink.Dim, Offset(left + 6f, cy - 3), Offset(left + 6f, cy + 3), 2f)
        drawLine(Ink.Dim, Offset(left + side - 6f, cy - 3), Offset(left + side - 6f, cy + 3), 2f)
    }
}

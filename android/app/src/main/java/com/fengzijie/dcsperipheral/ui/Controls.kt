package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.min

/**
 * 两个页面共用的控件。
 *
 * 抽出来不只是为了少写代码：飞行页和校准页必须显示**同一个**杆位盘，
 * 否则「在这个页面看着居中，到那个页面偏了」会让人怀疑是 bug。
 */

// ------------------------------------------------------------------ 杆位盘

/**
 * 杆位盘：一根横杆、一根竖杆、一个代表杆位的圆点，底部一条脚舵刻度。
 *
 * 为什么值得单独画一块：光看数字很难判断「我到底推了多少」，
 * 而杆位和飞机的响应是强耦合的。调死区和行程时能直接看到手抖有多大、
 * 离满杆还有多远；飞行中则能一眼确认「松手后真的回中了」——
 * 飘了就是该重新校零了。
 */
@Composable
fun StickPad(
    rollDeg: Float,
    pitchDeg: Float,
    yawDeg: Float,
    rangeDeg: Float,
    rudderRange: Float,
    armed: Boolean,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier) {
        val left = 4f
        val top = 4f
        val w = size.width - 8f
        val h = size.height - 8f
        val cx = left + w / 2f
        val cy = top + h / 2f
        val r = 10f

        drawRoundRect(
            color = Ink.Surface,
            topLeft = Offset(left, top),
            size = Size(w, h),
            cornerRadius = CornerRadius(r, r),
        )
        drawRoundRect(
            color = Ink.Line,
            topLeft = Offset(left, top),
            size = Size(w, h),
            cornerRadius = CornerRadius(r, r),
            style = Stroke(width = 1.5f),
        )

        // 十字与半杆网格
        drawLine(Ink.Line, Offset(left, cy), Offset(left + w, cy), strokeWidth = 1f)
        drawLine(Ink.Line, Offset(cx, top), Offset(cx, top + h), strokeWidth = 1f)
        val d = min(w, h) * 0.25f
        val g = Ink.Line.copy(alpha = 0.4f)
        drawLine(g, Offset(cx - d, top), Offset(cx - d, top + h), 1f)
        drawLine(g, Offset(cx + d, top), Offset(cx + d, top + h), 1f)
        drawLine(g, Offset(left, cy - d), Offset(left + w, cy - d), 1f)
        drawLine(g, Offset(left, cy + d), Offset(left + w, cy + d), 1f)

        // 杆位点：用原始角度除以行程定位，而不是曲线后的输出值 ——
        // 曲线是给飞机看的，人调手感时需要看真实的物理倾斜。
        val span = rangeDeg.coerceAtLeast(1f)
        val dx = (rollDeg / span).coerceIn(-1f, 1f) * (w / 2f - 10f)
        val dy = -(pitchDeg / span).coerceIn(-1f, 1f) * (h / 2f - 10f)
        val dotColor = if (armed) Ink.Teal else Ink.Dim
        if (armed) {
            drawCircle(dotColor.copy(alpha = 0.15f), radius = 24f, center = Offset(cx + dx, cy + dy))
        }
        drawCircle(dotColor, radius = 8f, center = Offset(cx + dx, cy + dy))
        drawCircle(
            Color.Black.copy(alpha = 0.45f), radius = 8f,
            center = Offset(cx + dx, cy + dy), style = Stroke(1.5f),
        )

        // 四向短刻度，帮判断握法对不对（下边留给脚舵刻度）
        val tick = Ink.Dim
        drawLine(tick, Offset(cx - 3, top + 6f), Offset(cx + 3, top + 6f), 2f)
        drawLine(tick, Offset(left + 6f, cy - 3), Offset(left + 6f, cy + 3), 2f)
        drawLine(tick, Offset(left + w - 6f, cy - 3), Offset(left + w - 6f, cy + 3), 2f)

        // 脚舵刻度：画在盘**内**底部，避免看起来像一条飘在外面的杂线。
        // 两件事都看得到：拧手机有没有生效，以及**滚转时有没有带出多余的
        // 偏航**（握姿不对时这个耦合特别明显）。
        val ry = top + h - 13f
        val rx0 = cx - min(w, h) * 0.32f
        val rx1 = cx + min(w, h) * 0.32f
        drawLine(Ink.Line, Offset(rx0, ry), Offset(rx1, ry), 3f)
        drawLine(Ink.Dim.copy(alpha = 0.7f), Offset(cx, ry - 4f), Offset(cx, ry + 4f), 1.5f)
        val rSpan = rudderRange.coerceAtLeast(1f)
        val rdx = (yawDeg / rSpan).coerceIn(-1f, 1f) * ((rx1 - rx0) / 2f)
        drawRoundRect(
            color = if (armed) Ink.Amber else Ink.Dim,
            topLeft = Offset(cx + rdx - 4f, ry - 5f),
            size = Size(8f, 10f),
            cornerRadius = CornerRadius(2f, 2f),
        )
    }
}

// ------------------------------------------------------------------ 油门

/**
 * 油门竖条。
 *
 * 用**相对拖动**而不是「点哪里跳到哪里」：绝对定位下，飞行中一根误触的
 * 手指就能把油门甩到满推力。相对拖动要真的划一下才动，慢半拍但安全。
 *
 * `taken == false` 时是灰色：表示用户还没接管，此时油门值根本不发给飞机
 * （见 YokeController 的保持类通道说明）。第一次碰它就变成接管状态。
 */
@Composable
fun ThrottleStrip(
    value: Float,
    taken: Boolean,
    armed: Boolean,
    onNudge: (Float) -> Unit,
    modifier: Modifier = Modifier,
) {
    val live = taken && armed
    val accent = when {
        live -> Ink.Teal
        taken -> Ink.Amber
        else -> Ink.Dim
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Ink.Surface)
            .border(
                1.dp,
                if (live) Ink.Teal.copy(alpha = 0.55f) else Ink.Line,
                RoundedCornerShape(10.dp),
            )
            .pointerInput(Unit) {
                detectDragGestures { change, dragAmount ->
                    change.consume()
                    // 手指往上 = 加油。用整条高度做满量程，一次从底划到顶
                    // 正好 0→100%，细调时 1dp 约 0.36%，够用。
                    onNudge(-dragAmount.y / size.height)
                }
            },
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val pad = 6f
            val trackL = size.width * 0.30f
            val trackR = size.width * 0.70f
            val trackT = pad + 26f          // 顶部给「油门」两个字留位
            val trackB = size.height - pad - 24f
            val th = trackB - trackT
            if (th <= 0f) return@Canvas

            drawRoundRect(
                color = Ink.Bg,
                topLeft = Offset(trackL, trackT),
                size = Size(trackR - trackL, th),
                cornerRadius = CornerRadius(6f, 6f),
            )
            val fh = th * value.coerceIn(0f, 1f)
            if (fh > 0f) {
                drawRoundRect(
                    color = accent,
                    topLeft = Offset(trackL, trackB - fh),
                    size = Size(trackR - trackL, fh),
                    cornerRadius = CornerRadius(6f, 6f),
                )
            }
            // 25 / 50 / 75 三道参考刻度
            for (k in 1..3) {
                val y = trackB - th * (k / 4f)
                drawLine(Ink.Line, Offset(trackL - 3f, y), Offset(trackL - 1f, y), 1.5f)
            }
            drawRoundRect(
                color = accent.copy(alpha = 0.8f),
                topLeft = Offset(trackL, trackB - fh - 1.5f),
                size = Size(trackR - trackL, 3f),
                cornerRadius = CornerRadius(1.5f, 1.5f),
            )
        }

        Column(
            modifier = Modifier.fillMaxSize().padding(vertical = 6.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("油门", color = accent, fontSize = 10.sp, maxLines = 1, softWrap = false)
            // 没接管时也显示数值：它代表「碰一下会发出去多少」。显示「--」
            // 的话，用户不知道第一次触摸会把油门带到哪里。
            Text(
                text = "${(value * 100).toInt()}",
                color = accent,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
}

// ------------------------------------------------------------------ 视角

/**
 * 视角摇杆：按住哪里，视角就往哪里偏，松手回中。
 *
 * 用「相对中心」的绝对映射而不是相对拖动 —— 视角和油门相反，它本来就是
 * 回中类控制，绝对映射符合摇杆的直觉，而且带视觉反馈（能看到自己压了多少）。
 */
@Composable
fun ViewPad(
    vx: Float,
    vy: Float,
    enabled: Boolean,
    onChange: (Float, Float) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var touching by remember { mutableStateOf(false) }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Ink.Surface)
            .border(1.dp, if (touching) Ink.Teal.copy(alpha = 0.55f) else Ink.Line, RoundedCornerShape(10.dp))
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown()
                    val cx = size.width / 2f
                    val cy = size.height / 2f
                    fun emit(p: Offset) {
                        onChange(
                            ((p.x - cx) / (size.width / 2f)).coerceIn(-1f, 1f),
                            (-(p.y - cy) / (size.height / 2f)).coerceIn(-1f, 1f),
                        )
                    }
                    touching = true
                    emit(down.position)
                    down.consume()
                    while (true) {
                        val ev = awaitPointerEvent()
                        val ch = ev.changes.firstOrNull { it.id == down.id } ?: break
                        if (!ch.pressed) break
                        emit(ch.position)
                        ch.consume()
                    }
                    touching = false
                    onRelease()
                }
            },
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val cx = size.width / 2f
            val cy = size.height / 2f
            drawLine(Ink.Line, Offset(0f, cy), Offset(size.width, cy), 1f)
            drawLine(Ink.Line, Offset(cx, 0f), Offset(cx, size.height), 1f)
            val g = Ink.Line.copy(alpha = 0.45f)
            drawCircle(g, radius = min(size.width, size.height) * 0.32f, center = Offset(cx, cy), style = Stroke(1f))

            if (touching) {
                val px = cx + vx * (size.width / 2f - 10f)
                val py = cy - vy * (size.height / 2f - 10f)
                drawCircle(Ink.Teal.copy(alpha = 0.16f), radius = 18f, center = Offset(px, py))
                drawCircle(Ink.Teal, radius = 7f, center = Offset(px, py))
            }
            drawCircle(Ink.Dim.copy(alpha = 0.5f), radius = 3f, center = Offset(cx, cy))
        }

        if (!touching) {
            Text(
                "视角\n按住拖动",
                color = Ink.Dim.copy(alpha = 0.55f),
                fontSize = 10.sp,
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp),
            )
        }
    }
}

// ------------------------------------------------------------------ 小件

@Composable
fun Chip(
    text: String,
    on: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .height(32.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Ink.Teal.copy(alpha = 0.18f) else Ink.Surface)
            .border(1.dp, if (on) Ink.Teal.copy(alpha = 0.7f) else Ink.Line, RoundedCornerShape(8.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            color = if (on) Ink.Teal else Ink.Dim,
            fontSize = 11.sp,
            maxLines = 1,
            softWrap = false,
        )
    }
}

/**
 * 按住才生效的按钮（襟翼、起落架）。
 *
 * 为什么同时上报「按下」和「松开」而不是只报一次点击：DCS 里襟翼有的机型
 * 是「点一下就动一格」，有的是「按住连续动」。两个边沿都发出去，两种都能用。
 * 最短脉宽由 YokeController 兜底，这里只管状态。
 */
@Composable
fun HoldButton(
    text: String,
    sub: String?,
    enabled: Boolean,
    onDown: () -> Unit,
    onUp: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var pressed by remember { mutableStateOf(false) }
    val fg = if (!enabled) Ink.Dim.copy(alpha = 0.45f) else if (pressed) Ink.Bg else Ink.Fg
    val bg = if (!enabled) Ink.Surface.copy(alpha = 0.5f)
    else if (pressed) Ink.Teal else Ink.Surface
    Box(
        modifier = modifier
            .fillMaxHeight()
            .clip(RoundedCornerShape(9.dp))
            .background(bg)
            .border(1.dp, if (pressed) Ink.Teal else Ink.Line, RoundedCornerShape(9.dp))
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                detectTapGestures(
                    onPress = {
                        pressed = true
                        onDown()
                        tryAwaitRelease()
                        pressed = false
                        onUp()
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text, color = fg, fontSize = 13.sp, fontWeight = FontWeight.Medium, maxLines = 1)
            if (sub != null) {
                Text(sub, color = fg.copy(alpha = 0.6f), fontSize = 8.sp, maxLines = 1)
            }
        }
    }
}

/**
 * 参数调节行。
 *
 * 用步进按钮而不是 Material Slider，是因为横屏可用高度只有 300 多 dp，
 * 几个滑块就要吃掉一半；而且手指在滑轨上很难精确停在 22°，步进一格一个
 * 确定值反而更快。说明文字与数值放在同一行，省下一整行高度。
 */
@Composable
fun Stepper(
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

/** 顶部状态点 + 一行字，用来解释「为什么杆不动」。 */
@Composable
fun StatusDot(color: Color, text: String, textColor: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(7.dp).background(color, CircleShape))
        Spacer(Modifier.width(6.dp))
        Text(text, color = textColor, fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

fun fmt1(v: Float): String = String.format(Locale.US, "%.1f", v)
fun fmt2s(v: Float): String = String.format(Locale.US, "%+.2f", v)

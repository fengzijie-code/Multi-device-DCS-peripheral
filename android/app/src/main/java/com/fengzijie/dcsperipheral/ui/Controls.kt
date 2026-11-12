package com.fengzijie.dcsperipheral.ui

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
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
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import kotlinx.coroutines.withTimeoutOrNull
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.abs
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
    rudder: Float,
    rangeDeg: Float,
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
        // 显示的是**最终给飞机的偏航量**，不是原始拧动角度 —— 这样无论
        // 来自拧手机还是滑块，看到的就是实际在起作用的那个值。
        val ry = top + h - 13f
        val rx0 = cx - min(w, h) * 0.32f
        val rx1 = cx + min(w, h) * 0.32f
        drawLine(Ink.Line, Offset(rx0, ry), Offset(rx1, ry), 3f)
        drawLine(Ink.Dim.copy(alpha = 0.7f), Offset(cx, ry - 4f), Offset(cx, ry + 4f), 1.5f)
        val rdx = rudder.coerceIn(-1f, 1f) * ((rx1 - rx0) / 2f)
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

// ------------------------------------------------------------------ 脚舵

/**
 * 脚舵滑块：横向，按住往左/右压，松手回中。
 *
 * 为什么还要做一个滑块，明明已经能用「拧手机」控制脚舵：
 *   拧手机是**看不见**的。屏幕上没有对应控件，用户根本不知道脚舵在哪，
 *   而且横滚时手腕会带出多余偏航 —— 这是物理耦合，软件只能淡化。
 *   滑块是显式的、可控的，两个通道可以并存：手指按在滑块上时以滑块为准，
 *   松开就回到拧手机。想彻底不用拧动，把校准页的「拧手机」关掉即可。
 *
 * 用绝对定位（压哪里就是多少）而不是相对拖动：脚舵是需要**持续压住**的
 * 轴，相对拖动意味着要一直划、一直累加，落地侧风时根本没法保持。
 */
@Composable
fun RudderBar(
    value: Float,
    enabled: Boolean,
    onSet: (Float) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var touching by remember { mutableStateOf(false) }
    val accent = if (enabled) Ink.Amber else Ink.Dim

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(9.dp))
            .background(Ink.Surface)
            .border(
                1.dp,
                if (touching) Ink.Amber.copy(alpha = 0.55f) else Ink.Line,
                RoundedCornerShape(9.dp),
            )
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown()
                    val cx = size.width / 2f
                    val half = (size.width / 2f) - 16f
                    fun emit(p: Offset) {
                        val v = ((p.x - cx) / half).coerceIn(-1f, 1f)
                        // 中位一个很窄的死区：手指想「回到正中」时很难精确停在
                        // 中线上，不给死区会一直残留一两度的偏航
                        onSet(if (abs(v) < 0.06f) 0f else v)
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
            val cy = size.height / 2f
            val half = (size.width / 2f) - 16f
            val th = size.height * 0.16f

            // 轨道
            drawRoundRect(
                color = Ink.Bg,
                topLeft = Offset(16f, cy - th / 2f),
                size = Size(size.width - 32f, th),
                cornerRadius = CornerRadius(th / 2f, th / 2f),
            )
            // 从中点向当前偏转方向填充：一眼就能看出偏了多少、偏哪边
            val v = value.coerceIn(-1f, 1f)
            if (abs(v) > 0.005f) {
                val x0 = size.width / 2f
                val x1 = x0 + v * half
                drawRoundRect(
                    color = accent.copy(alpha = 0.55f),
                    topLeft = Offset(min(x0, x1), cy - th / 2f),
                    size = Size(abs(x1 - x0), th),
                    cornerRadius = CornerRadius(th / 2f, th / 2f),
                )
            }
            // 中点凹口 + 两端刻度
            drawLine(Ink.Dim, Offset(size.width / 2f, cy - size.height * 0.24f),
                Offset(size.width / 2f, cy + size.height * 0.24f), 2f)
            for (f in floatArrayOf(-1f, 1f)) {
                val x = size.width / 2f + f * half
                drawLine(Ink.Dim.copy(alpha = 0.5f), Offset(x, cy - size.height * 0.14f),
                    Offset(x, cy + size.height * 0.14f), 1.5f)
            }
            // 滑块
            val px = size.width / 2f + v * half
            val tw = 16f
            val thh = size.height * 0.56f
            drawRoundRect(
                color = accent,
                topLeft = Offset(px - tw / 2f, cy - thh / 2f),
                size = Size(tw, thh),
                cornerRadius = CornerRadius(4f, 4f),
            )
            drawRoundRect(
                color = Color.Black.copy(alpha = 0.35f),
                topLeft = Offset(px - tw / 2f, cy - thh / 2f),
                size = Size(tw, thh),
                cornerRadius = CornerRadius(4f, 4f),
                style = Stroke(1.5f),
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
    enabled: Boolean,
    onChange: (Float, Float) -> Unit,
    onRelease: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var touching by remember { mutableStateOf(false) }
    // 点画在**手指相对按下点的位移**上，不画在映射后的 vx/vy 上：
    // 开了横纵互换或反转以后映射值和手指位置对不上，照映射值画会让点
    // 跑向反方向，像坏了。
    var dotX by remember { mutableStateOf(0f) }
    var dotY by remember { mutableStateOf(0f) }
    var baseX by remember { mutableStateOf(0f) }
    var baseY by remember { mutableStateOf(0f) }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Ink.Surface)
            .border(1.dp, if (touching) Ink.Teal.copy(alpha = 0.55f) else Ink.Line, RoundedCornerShape(10.dp))
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown()
                    // **相对按下点**，不是相对面板中心。
                    //
                    // 绝对定位（按到哪算到哪）有个隐蔽的副作用：手指一按下去，
                    // 两个轴同时跳到一个较大的值。在 DCS 里绑轴时 DCS 是
                    // 「动一下它自己认」，于是只要按得偏上一点，它就把
                    // 「Horizontal View」认成 JOY_RY —— 这正是用户遇到的情况。
                    // 改成相对以后，按下瞬间恒为零，只有拖动才产生偏转，
                    // 顺手也把手感改好了（不会一碰就甩到底）。
                    val ox = down.position.x
                    val oy = down.position.y
                    baseX = ox
                    baseY = oy
                    val r = min(size.width, size.height) / 2f - 10f
                    fun emit(p: Offset) {
                        val nx = ((p.x - ox) / r).coerceIn(-1f, 1f)
                        val ny = (-(p.y - oy) / r).coerceIn(-1f, 1f)
                        dotX = nx; dotY = ny
                        onChange(nx, ny)
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
            val r = min(size.width, size.height) / 2f - 10f
            drawLine(Ink.Line, Offset(0f, cy), Offset(size.width, cy), 1f)
            drawLine(Ink.Line, Offset(cx, 0f), Offset(cx, size.height), 1f)

            if (touching) {
                // 按下点画一个底盘，手指偏出去多少一目了然
                drawCircle(
                    Ink.Line, radius = r, center = Offset(baseX, baseY),
                    style = Stroke(1.5f),
                )
                val px = baseX + dotX * r
                val py = baseY - dotY * r
                drawCircle(Ink.Teal.copy(alpha = 0.16f), radius = 16f, center = Offset(px, py))
                drawCircle(Ink.Teal, radius = 7f, center = Offset(px, py))
            } else {
                drawCircle(Ink.Dim.copy(alpha = 0.5f), radius = 3f, center = Offset(cx, cy))
            }
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
 * 带保护的按住按钮（战斗页的发射 / 锁定 / 切武器）。
 *
 * 和 [HoldButton] 的区别：手指按下后先等 [guardMs]，这期间抬手就什么都不发。
 * 只有按够时间才真正把「按下」发出去，之后松手再发「松开」。
 *
 * 为什么需要这道门槛：触摸屏没有物理边界，手指从按钮上划过（按下和抬起
 * 都在按钮内，总时长几十毫秒）就是一次完整点击。用来开火的话，一次划过
 * 就是一枚导弹出去了 —— 不可逆，也不能靠「小心一点」避免。
 *
 * 200ms 这个量级是有讲究的：短到不影响机炮连射的手感（按住就开始打），
 * 又长到足以滤掉所有「划过」。代价是任何操作都慢 200ms，所以只给真正
 * 不可逆的动作加，切武器这种能反悔的就不用。
 */
@Composable
fun GuardButton(
    text: String,
    sub: String? = null,
    enabled: Boolean,
    onDown: () -> Unit,
    onUp: () -> Unit,
    modifier: Modifier = Modifier,
    guardMs: Int = 200,
    danger: Boolean = false,
) {
    var holding by remember { mutableStateOf(false) }
    val prog = remember { Animatable(0f) }
    val accent = if (danger) Ink.Red else Ink.Amber

    LaunchedEffect(holding) {
        if (holding) {
            prog.animateTo(1f, tween(durationMillis = guardMs, easing = LinearEasing))
        } else {
            prog.snapTo(0f)
        }
    }

    Box(
        modifier = modifier
            .clip(RoundedCornerShape(10.dp))
            .background(if (danger) Ink.Red.copy(alpha = 0.13f) else Ink.Surface)
            .border(
                1.dp,
                when {
                    holding -> accent
                    danger -> Ink.Red.copy(alpha = 0.55f)
                    else -> Ink.Line
                },
                RoundedCornerShape(10.dp),
            )
            .pointerInput(enabled, guardMs) {
                if (!enabled) return@pointerInput
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    holding = true
                    // 超时返回 null = 手指还按着（够格了）；提前抬手返回非 null。
                    // 用 withTimeoutOrNull 包住等待而不是自己起计时协程：
                    // 这样手势状态不会被破坏，后面还能再等一次真正的抬起。
                    val upEarly = withTimeoutOrNull(guardMs.toLong()) { waitForUpOrCancellation() }
                    if (upEarly == null) {
                        onDown()
                        waitForUpOrCancellation()
                        onUp()
                    }
                    holding = false
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(prog.value.coerceIn(0f, 1f))
                .background(accent.copy(alpha = 0.16f)),
        )
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = text,
                color = when {
                    holding -> accent
                    danger -> Ink.Red
                    enabled -> Ink.Fg
                    else -> Ink.Dim
                },
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                softWrap = false,
            )
            if (sub != null) {
                Text(
                    text = sub,
                    color = Ink.Dim,
                    fontSize = 10.sp,
                    maxLines = 1,
                    softWrap = false,
                )
            }
        }
    }
}

/**
 * 配平按钮（force trim）。
 *
 * 单击 = 把当前杆位记成配平量，松手后停在这儿。
 * 长按 = 清零。
 *
 * 为什么不像校零那样要求长按才能触发：直升机飞行员是一边压杆一边配平的，
 * 要求按住 0.7 秒根本没法用。而且配平点错了可以再点一次纠正，
 * 不像校零 —— 校零会把传感器零点写坏，那个才必须防误触。
 *
 * 反过来「长按清除」是刻意的：清除会把飞机交回中立杆位，飞行中是个
 * 姿态突变，值得多一道门槛。
 */
@Composable
fun TrimButton(
    trim: Float,
    enabled: Boolean,
    onCapture: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val active = trim != 0f
    Box(
        modifier = modifier
            // 高度跟着所在的那一行走（现在是襟翼/起落架那一行，46dp）。
            // 内部不再写死高度，否则会盖掉调用方的 fillMaxHeight。
            .fillMaxHeight()
            .clip(RoundedCornerShape(8.dp))
            .background(if (active) Ink.Amber.copy(alpha = 0.16f) else Ink.Surface)
            .border(
                1.dp,
                if (active) Ink.Amber.copy(alpha = 0.65f) else Ink.Line,
                RoundedCornerShape(8.dp),
            )
            .pointerInput(enabled) {
                if (!enabled) return@pointerInput
                detectTapGestures(
                    onTap = { onCapture() },
                    onLongPress = { onClear() },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                // 有配平时直接把数字摆在主行 —— 飞行中最想知道的是「现在偏了多少」，
                // 而不是「有没有配平」。
                text = if (active) "${if (trim > 0) "+" else ""}${(trim * 100).toInt()}%" else "配平",
                color = if (active) Ink.Amber else if (enabled) Ink.Fg else Ink.Dim,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                softWrap = false,
            )
            Text(
                text = if (active) "长按清零" else "单击生效",
                color = Ink.Dim,
                fontSize = 10.sp,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
}

/**
 * 长按才生效的按钮（校零 / 调参）。**防误触专用。**
 *
 * 为什么需要它：这两个按钮紧贴在视角 pad 下面，手指在 pad 上滑动很容易划出
 * 边界、落在按钮上，抬起就成了一次点击。后果不是「多点了一下」，而是：
 *   - 误触「校零」→ 把当前倾斜姿态当成中位存进去，之后杆的中立点全错；
 *   - 误触「调参」→ 直接跳走页面，摇杆停发，飞行中突然失去操纵。
 * 这两种都不能靠「小心一点」避免，只能靠交互门槛。
 *
 * 为什么选长按而不是「点两次」或「先点锁再点按钮」：
 *   误触的手指是**划过**，不会在同一点停留 700ms；真要校零时按住不放，也
 *   符合「这是个危险动作」的直觉。而且长按不需要维护锁状态，不会出现
 *   「以为锁着其实解锁了」的第二种错误。
 *
 * 视觉反馈三层：按住时文字变「按住…」、边框变琥珀色、底部进度条填满。
 * 填满的瞬间给一次震动 —— 手指挡住按钮时，触觉是唯一还看得见的反馈。
 */
@Composable
fun LockChip(
    text: String,
    on: Boolean,
    onRun: () -> Unit,
    modifier: Modifier = Modifier,
    holdMs: Int = 700,
) {
    val haptic = LocalHapticFeedback.current
    var holding by remember { mutableStateOf(false) }
    val prog = remember { Animatable(0f) }

    // 进度条和计时用同一个时长常量，视觉填满 == 恰好触发。
    // 两者是独立计时，理论上会差几毫秒，但都是 700ms，人眼看不出。
    LaunchedEffect(holding) {
        if (holding) {
            prog.animateTo(1f, tween(durationMillis = holdMs, easing = LinearEasing))
        } else {
            prog.snapTo(0f)
        }
    }

    Box(
        modifier = modifier
            .height(36.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Ink.Teal.copy(alpha = 0.18f) else Ink.Surface)
            .border(
                1.dp,
                when {
                    holding -> Ink.Amber
                    on -> Ink.Teal.copy(alpha = 0.7f)
                    else -> Ink.Line
                },
                RoundedCornerShape(8.dp),
            )
            .pointerInput(holdMs) {
                detectTapGestures(
                    onPress = {
                        holding = true
                        // 超时返回 null = 按够了；提前松手（或滑出边界）返回 true。
                        // tryAwaitRelease 自己会区分「正常抬起」和「手势被取消」，
                        // 但两种情况都不该触发，所以这里只认超时。
                        val released = withTimeoutOrNull(holdMs.toLong()) {
                            tryAwaitRelease()
                            true
                        }
                        holding = false
                        if (released == null) {
                            prog.snapTo(0f)
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                            onRun()
                        }
                    },
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        // 进度填充画在文字下面，不挡字
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(prog.value.coerceIn(0f, 1f))
                .background(if (on) Ink.Teal.copy(alpha = 0.30f) else Ink.Amber.copy(alpha = 0.22f)),
        )
        Text(
            text = if (holding) "按住…" else text,
            color = if (holding) Ink.Amber else if (on) Ink.Teal else Ink.Dim,
            fontSize = 10.sp,
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

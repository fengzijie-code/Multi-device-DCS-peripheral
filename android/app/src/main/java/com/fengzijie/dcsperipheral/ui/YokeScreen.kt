package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fengzijie.dcsperipheral.input.YokeSettings
import com.fengzijie.dcsperipheral.input.YokeState
import java.util.Locale

/** 按钮编号 = vJoy 按钮号 - 1。改这里就等于改 DCS 里绑哪个键。 */
object YokeBtn {
    const val FLAPS_UP = 0
    const val FLAPS_DOWN = 1
    const val GEAR = 2
}

/**
 * 飞行页 —— 手握着手机不放就能完成全部操作。
 *
 * 版面从左到右按「离手多远」排：油门贴在左边缘（左拇指），杆位盘居中
 * （只是显示，不用碰），视角摇杆偏右（右拇指），按钮在左右两端。
 * 这样不用挪动手掌就能同时够到油门和视角。
 *
 * 杆位盘在这一页只显示不响应触摸 —— 飞行中误触一个可交互区域比少一个
 * 功能危险得多。
 */
@Composable
fun YokeScreen(
    st: YokeState,
    set: YokeSettings,
    onThrottle: (Float) -> Unit,
    onRudder: (Float) -> Unit,
    onRudderRelease: () -> Unit,
    onView: (Float, Float) -> Unit,
    onViewRelease: () -> Unit,
    onButtonDown: (Int) -> Unit,
    onButtonUp: (Int) -> Unit,
    onToggleArm: () -> Unit,
    onCalibrate: () -> Unit,
    onSettings: () -> Unit,
    onTrimCapture: () -> Unit,
    onTrimClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier = modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        // ---------------- 左：油门 ----------------
        ThrottleStrip(
            value = st.throttle,
            taken = st.throttleTaken,
            armed = st.armed,
            onNudge = onThrottle,
            modifier = Modifier.width(62.dp).fillMaxHeight(),
        )

        // ---------------- 中：杆位 + 脚舵 + 动作按钮 ----------------
        Column(Modifier.weight(1f).fillMaxHeight()) {
            StickPad(
                rollDeg = st.rollDeg,
                pitchDeg = st.pitchDeg,
                rudder = st.rudder,
                rangeDeg = set.rangeDeg,
                armed = st.armed,
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )
            Spacer(Modifier.height(5.dp))

            // 配平紧贴杆位盘：它是「把杆锁在这儿」的动作，离杆越近越直觉。
            // 直升机专用 —— 固定翼上它保持中性（不按就一直是 0），不影响。
            TrimButton(
                trim = st.trimY,
                enabled = st.armed,
                onCapture = onTrimCapture,
                onClear = onTrimClear,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(5.dp))

            // 脚舵单列一行，带文字标签。之前只靠「拧手机」，屏幕上没有
            // 任何可见控件 —— 用户根本不知道脚舵在哪。可见性比优雅重要。
            Row(
                Modifier.fillMaxWidth().height(34.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "脚舵",
                    color = if (st.armed) Ink.Amber else Ink.Dim,
                    fontSize = 10.sp,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.width(30.dp),
                )
                RudderBar(
                    value = st.rudder,
                    enabled = st.armed,
                    onSet = onRudder,
                    onRelease = onRudderRelease,
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                )
            }

            Spacer(Modifier.height(5.dp))
            Row(
                Modifier.fillMaxWidth().height(46.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                HoldButton(
                    text = "襟翼↑",
                    sub = "收起",
                    enabled = st.armed,
                    onDown = { onButtonDown(YokeBtn.FLAPS_UP) },
                    onUp = { onButtonUp(YokeBtn.FLAPS_UP) },
                    modifier = Modifier.weight(1f),
                )
                HoldButton(
                    text = "襟翼↓",
                    sub = "放下",
                    enabled = st.armed,
                    onDown = { onButtonDown(YokeBtn.FLAPS_DOWN) },
                    onUp = { onButtonUp(YokeBtn.FLAPS_DOWN) },
                    modifier = Modifier.weight(1f),
                )
                HoldButton(
                    text = "起落架",
                    sub = "收放",
                    enabled = st.armed,
                    onDown = { onButtonDown(YokeBtn.GEAR) },
                    onUp = { onButtonUp(YokeBtn.GEAR) },
                    modifier = Modifier.weight(1f),
                )
            }
        }

        // ---------------- 右：解锁 / 状态 / 视角 ----------------
        Column(Modifier.width(272.dp).fillMaxHeight()) {
            ArmButton(armed = st.armed, ready = st.ready, onClick = onToggleArm)

            Spacer(Modifier.height(3.dp))
            VjoyLine(st.vjoy)

            Spacer(Modifier.height(2.dp))
            // 有提示时优先显示提示：自动上锁的原因比链路数字重要得多
            if (st.notice != null) {
                Text(
                    text = st.notice,
                    color = Ink.Amber,
                    fontSize = 10.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            } else {
                Text(
                    text = "链路 ${st.rttMs} ms · ${fmt1(st.hz)} Hz",
                    color = Ink.Dim,
                    fontSize = 10.sp,
                    fontFamily = FontFamily.Monospace,
                    maxLines = 1,
                )
            }

            Spacer(Modifier.height(4.dp))
            ViewPad(
                enabled = st.armed,
                onChange = onView,
                onRelease = onViewRelease,
                modifier = Modifier.weight(1f).fillMaxWidth(),
            )

            // 间距从 4dp 拉到 10dp：光靠长按还不够，手指从 pad 滑出来时先
            // 撞到空白区域，比直接压在按钮上更容易「反应过来就松手」。
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth().height(36.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                LockChip(
                    text = if (st.hasNeutral) "长按·重新校零" else "长按·校零",
                    on = !st.hasNeutral,
                    onRun = onCalibrate,
                    modifier = Modifier.weight(1f),
                )
                LockChip(
                    text = "长按·调参",
                    on = false,
                    onRun = onSettings,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

/**
 * vJoy 状态行。
 *
 * 操纵链有五跳（手机→桥接→vjoy_out→驱动→DCS），任一跳断了现象都是
 * 「杆不动」。这一行专门用来指出断在第几跳之后，省掉一轮瞎猜。
 */
@Composable
private fun VjoyLine(state: Int) {
    when (state) {
        1 -> StatusDot(Ink.Teal, "虚拟摇杆就绪", Ink.Dim)
        2 -> StatusDot(Ink.Amber, "摇杆缺轴 · 查 Configure vJoy", Ink.Amber)
        else -> StatusDot(Ink.Amber, "虚拟摇杆未运行 · 杆不会动", Ink.Amber)
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
            .height(46.dp)
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

/**
 * 校准页 —— 上电后调一次，之后偶尔重新校零。
 *
 * 和飞行页分开，是因为飞行页要留给真正会动的控件。两页共用同一个杆位盘，
 * 所以「这一页看着居中，那一页也一定居中」。
 */
@Composable
fun CalibScreen(
    st: YokeState,
    set: YokeSettings,
    onSettings: (YokeSettings) -> Unit,
    onCalibrate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier = modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        // 正方形：杆位盘的横纵增益必须一致，否则「推一半」在两轴上看着不一样
        Box(Modifier.weight(1f).fillMaxHeight(), contentAlignment = Alignment.Center) {
            StickPad(
                rollDeg = st.rollDeg,
                pitchDeg = st.pitchDeg,
                rudder = st.rudder,
                rangeDeg = set.rangeDeg,
                armed = st.armed,
                modifier = Modifier.fillMaxHeight().aspectRatio(1f),
            )
        }
        Column(
            Modifier
                .width(392.dp)
                .fillMaxHeight()
                // 参数行加了一行就会顶到折叠线以下。滚动是廉价的保险，
                // 免得以后再加参数时又要在小屏上排查「看不见的那一项」。
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Chip(
                    text = if (st.hasNeutral) "重新校零" else "校零",
                    on = !st.hasNeutral,
                    onClick = onCalibrate,
                    modifier = Modifier.weight(1.2f),
                )
                Chip(
                    text = if (set.swapAxes) "横握" else "竖握",
                    on = true,
                    onClick = { onSettings(set.copy(swapAxes = !set.swapAxes)) },
                    modifier = Modifier.weight(0.8f),
                )
                Chip(
                    // 只控制「拧手机」这个来源。滑块在飞行页上始终可用 ——
                    // 关掉拧动的人不应该连脚舵一起失去。
                    text = if (set.rudderOn) "拧手机 开" else "拧手机 关",
                    on = set.rudderOn,
                    onClick = { onSettings(set.copy(rudderOn = !set.rudderOn)) },
                    modifier = Modifier.weight(1f),
                )
            }
            // 四个方向开关分两行两列，比挤成一行四个窄条好点
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Chip(
                    text = if (set.invertX) "左右 反转" else "左右 正常",
                    on = set.invertX,
                    onClick = { onSettings(set.copy(invertX = !set.invertX)) },
                    modifier = Modifier.weight(1f),
                )
                Chip(
                    text = if (set.invertY) "前后 反转" else "前后 正常",
                    on = set.invertY,
                    onClick = { onSettings(set.copy(invertY = !set.invertY)) },
                    modifier = Modifier.weight(1f),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Chip(
                    text = if (set.invertRudder) "脚舵 反转" else "脚舵 正常",
                    on = set.invertRudder,
                    onClick = { onSettings(set.copy(invertRudder = !set.invertRudder)) },
                    modifier = Modifier.weight(1f),
                )
                Chip(
                    // 这个开关以前只存在于设置结构里，界面上没有入口 —— 等于不存在。
                    // 油门方向反了的人会卡在这里，因为他根本找不到地方翻。
                    text = if (set.throttleInvert) "油门 反转" else "油门 正常",
                    on = set.throttleInvert,
                    onClick = { onSettings(set.copy(throttleInvert = !set.throttleInvert)) },
                    modifier = Modifier.weight(1f),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Chip(
                    // 这三个是给「DCS 自动识别认错轴」准备的。DCS 绑定轴时
                    // 是「动一下它自己认」，横着拖的时候如果手指按得偏上/偏下，
                    // 它可能认成另一根轴。重绑很烦，这里互换一下就行。
                    text = if (set.swapViewAxes) "视角 横纵互换" else "视角 横纵正常",
                    on = set.swapViewAxes,
                    onClick = { onSettings(set.copy(swapViewAxes = !set.swapViewAxes)) },
                    modifier = Modifier.weight(1.3f),
                )
                Chip(
                    text = if (set.invertViewX) "视角横 反转" else "视角横 正常",
                    on = set.invertViewX,
                    onClick = { onSettings(set.copy(invertViewX = !set.invertViewX)) },
                    modifier = Modifier.weight(1f),
                )
                Chip(
                    text = if (set.invertViewY) "视角纵 反转" else "视角纵 正常",
                    on = set.invertViewY,
                    onClick = { onSettings(set.copy(invertViewY = !set.invertViewY)) },
                    modifier = Modifier.weight(1f),
                )
            }
            Stepper(
                label = "拧舵行程",
                value = "${set.rudderRangeDeg.toInt()}°",
                hint = "拧手机多少度算满舵（滑块不受影响）",
                onMinus = {
                    onSettings(set.copy(rudderRangeDeg = (set.rudderRangeDeg - 2f).coerceAtLeast(8f)))
                },
                onPlus = {
                    onSettings(set.copy(rudderRangeDeg = (set.rudderRangeDeg + 2f).coerceAtMost(60f)))
                },
            )

            Stepper(
                label = "行程",
                value = "${set.rangeDeg.toInt()}°",
                hint = "推满要倾斜多少度",
                onMinus = { onSettings(set.copy(rangeDeg = (set.rangeDeg - 1f).coerceAtLeast(8f))) },
                onPlus = { onSettings(set.copy(rangeDeg = (set.rangeDeg + 1f).coerceAtMost(45f))) },
            )
            Stepper(
                label = "死区",
                value = fmt1(set.deadbandDeg) + "°",
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
            Stepper(
                label = "脚舵死区",
                value = fmt1(set.rudderDeadbandDeg) + "°",
                hint = "拧手机时中位附近算没动",
                onMinus = {
                    onSettings(set.copy(rudderDeadbandDeg = (set.rudderDeadbandDeg - 0.5f).coerceAtLeast(0f)))
                },
                onPlus = {
                    onSettings(set.copy(rudderDeadbandDeg = (set.rudderDeadbandDeg + 0.5f).coerceAtMost(15f)))
                },
            )
            if (st.notice != null) {
                Text(
                    text = st.notice,
                    color = Ink.Amber,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(horizontal = 2.dp),
                )
            }
        }
    }
}

package com.fengzijie.dcsperipheral.input

import android.content.Context
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.Locale
import kotlin.math.abs

/** 手感参数。全部可以在手机上实时调，不需要重编译。 */
data class YokeSettings(
    /** 中位附近多大角度内算「没动」。手持必然有微抖，不给死区杆会一直轻颤。 */
    val deadbandDeg: Float = 2.5f,
    /** 打到满杆需要倾斜多少度。越小越灵敏，也越累。 */
    val rangeDeg: Float = 22f,
    /** 曲线指数混合：0 = 线性，1 = 纯三次方（中间极细、末端仍满）。 */
    val expo: Float = 0.35f,
    val invertX: Boolean = false,
    /** 俯仰：实测这架飞机方向相反，默认翻过来。 */
    val invertY: Boolean = true,
    /** 横握（配合横屏 UI）：左右倾斜绕的是设备 X 轴，对应横滚。 */
    val swapAxes: Boolean = true,
    // ---- 脚舵：靠「拧手机」（绕屏幕法线旋转）----
    val rudderOn: Boolean = true,
    val rudderDeadbandDeg: Float = 4f,
    val rudderRangeDeg: Float = 28f,
    val invertRudder: Boolean = false,
    // ---- 油门 ----
    /** 油门方向：DCS 里这根轴是反的，默认翻过来。 */
    val throttleInvert: Boolean = true,
    // ---- 视角 ----
    /** 横纵互换。DCS 自动识别轴的时候容易认错，互换一下不用重绑。 */
    val swapViewAxes: Boolean = false,
    val invertViewX: Boolean = false,
    val invertViewY: Boolean = false,
)

/**
 * 配平偏移的上限。
 *
 * 不给到 1.0 是有意的：满杆配平等于「一解锁就压到底」，对固定翼是灾难，
 * 对直升机也几乎没有用处（真要满杆说明该检查重心/载重了）。0.7 足够压平
 * 大多数直升机的悬停与巡航偏差，又留了一点反应余量。
 */
private const val TRIM_MAX = 0.7f

data class YokeState(
    val armed: Boolean = false,
    val sensorOk: Boolean = false,
    val hasNeutral: Boolean = false,
    val ready: Boolean = false,
    /**
     * 杆位：手的**控制位置**，不是发给飞机的值。
     *
     * 后仰 → 这里为负 → 盘上点向下 → 机头抬起。和真机拉杆一致：手柄朝自己
     * （屏幕下方），机头向上。反转只改变发送值的符号，不改变这里。
     */
    val pitchDeg: Float = 0f,
    val rollDeg: Float = 0f,
    val yawDeg: Float = 0f,
    /** 实际发出去的量 */
    val x: Float = 0f,
    val y: Float = 0f,
    val r: Float = 0f,
    /** 最终的偏航量（-1..1），已含滑块优先、拧动、反转。杆位盘底部显示这个。 */
    val rudder: Float = 0f,
    val vx: Float = 0f,
    val vy: Float = 0f,
    /**
     * 配平偏移（force trim）。0 = 没配平。
     *
     * 语义是「松手后保持住这个杆位」，不是「把当前姿态当成新零点」：
     * 后者松手会回到中立，而直升机要的恰恰是**别**回中立。
     */
    val trimX: Float = 0f,
    val trimY: Float = 0f,
    /** 0..1；`throttleTaken` 为 false 时这个值不发给飞机 */
    val throttle: Float = 0f,
    val throttleTaken: Boolean = false,
    val buttons: Int = 0,
    val sent: Long = 0L,
    val hz: Float = 0f,
    val rttMs: Long = 0L,
    /** 0 = vjoy_out 没在跑  1 = 就绪  2 = 在跑但缺轴/缺按钮 */
    val vjoy: Int = 0,
    val notice: String? = null,
)

/**
 * 把手机变成一台六通道控制器。
 *
 * 通道：左右 / 前后 / 脚舵（拧手机）/ 油门（触摸）/ 视角横纵（触摸）/ 按钮。
 *
 * 三件事必须分开想，否则会写出「一卡全卡」的东西：
 *   1. 采传感器  —— 200Hz，在系统回调线程里，只做存四元数，绝不联网
 *   2. 算操纵量  —— 50Hz，在协程里，纯数学
 *   3. 发出去    —— 跟第 2 步同频，但可以失败、可以慢，失败了不能影响第 1 步
 *
 * ═══ 安全策略（这一段比功能重要）═══
 * 为什么要区分「回中类」和「保持类」通道：
 *   杆、脚舵、视角松手就该回零，断线归零是安全的。
 *   油门**不是** —— 它天生要停在原地。断线时把它拽回慢车，飞机在进近中
 *   会直接掉下去。所以油门有三重保护：
 *     · 未解锁不发（飞机保持自己的油门）
 *     · 用户没碰过滑块也不发（不会一解锁就把油门拽到 0）
 *     · PC 端看门狗只回中，不动油门
 *
 * 其余：
 *   - 默认**未解锁**，上电不会自己开始操纵飞机。
 *   - 网络一断立刻自动上锁，避免「链路恢复瞬间满杆回弹」。
 *   - 倾角超过阈值持续 400ms 自动上锁（手机掉了/放桌上）。
 */
class YokeController(
    context: Context,
    private val baseUrl: String,
) {
    private val app = context.applicationContext
    private val tilt = TiltSource(app)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val prefs = app.getSharedPreferences("dcs_peripheral", Context.MODE_PRIVATE)

    private val _state = MutableStateFlow(YokeState(sensorOk = tilt.available))
    val state: StateFlow<YokeState> = _state.asStateFlow()

    @Volatile var settings: YokeSettings = YokeSettings()
        private set

    @Volatile private var armed = false
    @Volatile private var vjoyFlag = 0
    @Volatile private var notice: String? = null
    private var job: Job? = null

    // ---- 配平（force trim）----
    //
    // 为什么需要它：手机是「绝对位置」映射，松手 = 轴回 0 = 杆回中立。
    // 固定翼没问题（杆中位就是平飞配平点），但直升机的中立周期变距**不是**
    // 平飞位：悬停/平飞往往要一直顶着杆。真实直升机靠 force trim 把杆位锁住，
    // 松手不停在那儿；我们没有力反馈杆，只能在软件里补这一层。
    //
    // 上限 0.7 而不是 1.0：满杆配平等于一起飞就压到底，太危险。
    // 0.7 足够压平大多数直升机的悬停/巡航偏差，又留了反应余量。
    @Volatile private var trimX = 0f
    @Volatile private var trimY = 0f
    // 「如果现在解锁，杆会在哪」。配平按钮拿它当新偏移，所以必须先减去旧偏移
    // 再加上去，否则连按两次会翻倍。
    @Volatile private var lastOutX = 0f
    @Volatile private var lastOutY = 0f

    private val url = "${baseUrl.trimEnd('/')}/input"

    // ---- 触摸类通道：UI 线程写，IO 线程读 ----
    //
    // 油门值要在进程重启后活下来。否则「空中 App 被杀 → 重启 → 第一次碰
    // 滑块」会把油门从上次的位置（比如 70%）瞬间拽到 0，等于空中收油门。
    // 只持久化**值**，不持久化「已接管」：新会话默认仍是不接管的状态，
    // 飞机保持自己的油门，直到用户真的去碰它。
    @Volatile private var throttle = prefs.getFloat("yk_throttle", 0f).coerceIn(0f, 1f)

    /** 用户碰过油门滑块没有。没碰过就绝不发油门 —— 见类注释。 */
    @Volatile private var throttleTaken = false
    @Volatile private var viewX = 0f
    @Volatile private var viewY = 0f
    @Volatile private var lastThrottleSave = 0L

    /**
     * 脚舵滑块当前值（-1..1）。null 表示手指没按在滑块上。
     *
     * 和拧手机并存：按着滑块时以滑块为准，松开回到拧动。两者同时生效会
     * 互相打架 —— 用户没法理解「为什么我明明没拧，脚舵还在偏」。
     */
    @Volatile private var rudderTouch: Float? = null

    // ---- 按钮 ----
    private val btnLock = Any()
    private var btnHeld = 0
    private var btnPulse = 0
    private val btnDeadline = LongArray(BUTTON_COUNT)

    fun start() {
        if (job?.isActive == true) return
        tilt.start()
        job = scope.launch { loop() }
    }

    fun stop() {
        // 停之前一定把「已上锁 + 全零」发出去，否则 PC 那边要等 500ms
        // 看门狗才回中，白白多一段时间的满杆
        armed = false
        viewX = 0f; viewY = 0f
        rudderTouch = null
        synchronized(btnLock) { btnHeld = 0; btnPulse = 0 }
        runCatching { post(0f, 0f, 0f, 0f, 0f, null, 0) }
        saveThrottle(force = true)
        job?.cancel()
        job = null
        tilt.stop()
        ch.close()
    }

    fun shutdown() {
        stop()
        scope.cancel()
    }

    fun updateSettings(s: YokeSettings) {
        settings = s
    }

    fun captureNeutral() {
        if (tilt.captureNeutral()) {
            notice = null
        } else {
            notice = "传感器还没出数据，等一秒再校零"
        }
    }

    fun setArmed(on: Boolean) {
        if (on && !tilt.hasNeutral) {
            notice = "先校零：把手机摆到舒服的位置，点「校零」"
            return
        }
        armed = on
        if (on) notice = null
        _state.value = _state.value.copy(armed = on, notice = notice)
    }

    fun toggleArmed() = setArmed(!armed)

    // ------------------------------------------------------------ 配平

    /**
     * 把当前杆位记成配平偏移：杆台此刻在哪，松手后就停在哪。
     *
     * 直接取 lastOut（已含旧偏移），所以连按两次不会翻倍，效果是「再微调一点」。
     */
    fun captureTrim() {
        trimX = lastOutX.coerceIn(-TRIM_MAX, TRIM_MAX)
        trimY = lastOutY.coerceIn(-TRIM_MAX, TRIM_MAX)
        notice = if (trimX == 0f && trimY == 0f) "配平已清零" else "已配平，松手保持"
    }

    fun clearTrim() {
        trimX = 0f
        trimY = 0f
        notice = "配平已清零"
    }

    // ------------------------------------------------------------ 触摸输入

    /** 相对拖动。绝对定位会让一根误触的手指直接把油门甩到满。 */
    fun nudgeThrottle(delta: Float) {
        throttleTaken = true
        throttle = (throttle + delta).coerceIn(0f, 1f)
        saveThrottle(force = false)
    }

    /** 界面上的 ±1% 微调按钮 */
    fun throttleStep(d: Float) = nudgeThrottle(d)

    private fun saveThrottle(force: Boolean) {
        val now = SystemClock.elapsedRealtime()
        if (!force && now - lastThrottleSave < 500) return
        lastThrottleSave = now
        prefs.edit().putFloat("yk_throttle", throttle).apply()
    }

    fun setView(x: Float, y: Float) {
        viewX = x.coerceIn(-1f, 1f)
        viewY = y.coerceIn(-1f, 1f)
    }

    fun releaseView() {
        viewX = 0f; viewY = 0f
    }

    /** 手指按在脚舵滑块上：以滑块为准。 */
    fun setRudder(v: Float) {
        rudderTouch = v.coerceIn(-1f, 1f)
    }

    /** 松开脚舵滑块：回中，交还给「拧手机」。 */
    fun releaseRudder() {
        rudderTouch = null
    }

    /**
     * 按下按钮。会保证至少 [MIN_PULSE_MS] 的按下时间 —— DCS 在每个模拟帧
     * 采样按钮状态，如果按下和抬起发生在同一次轮询之间，这一下就丢了。
     * 触摸屏上一次快速点按可能只有 20ms，所以必须由我们兜住。
     */
    fun pressButton(index: Int) {
        if (index !in 0 until BUTTON_COUNT) return
        synchronized(btnLock) {
            btnHeld = btnHeld or (1 shl index)
            btnPulse = btnPulse or (1 shl index)
            btnDeadline[index] = SystemClock.elapsedRealtime() + MIN_PULSE_MS
        }
    }

    fun releaseButton(index: Int) {
        if (index !in 0 until BUTTON_COUNT) return
        synchronized(btnLock) { btnHeld = btnHeld and (1 shl index).inv() }
    }

    private fun effectiveButtons(now: Long): Int {
        synchronized(btnLock) {
            var v = btnHeld
            var i = 0
            while (i < BUTTON_COUNT) {
                val bit = 1 shl i
                if (btnPulse and bit != 0) {
                    if (now < btnDeadline[i]) v = v or bit
                    else btnPulse = btnPulse and bit.inv()
                }
                i++
            }
            return v
        }
    }

    // ------------------------------------------------------------ 曲线

    /**
     * 死区 → 归一 → 曲线。
     *
     * 死区之后要**重新归一**（除以 range-deadband 而不是 range），
     * 否则死区边界上会有一个跳变：刚出死区就到 12% 杆量。
     * 这种小跳变在接近中位修正时特别难受。
     */
    private fun curve(raw: Float, deadband: Float, range: Float, expo: Float): Float {
        val a = abs(raw)
        if (a <= deadband) return 0f
        val span = (range - deadband).coerceAtLeast(1f)
        val v = ((a - deadband) / span).coerceAtMost(1f)
        // 经典 RC 指数曲线：(1-e)·v + e·v³。端点仍是 0 和 1，中间被压细
        val out = v * (1f - expo) + v * v * v * expo
        return if (raw < 0f) -out else out
    }

    // ------------------------------------------------------------ 主循环

    private suspend fun loop() {
        val periodMs = 20L                 // 50Hz
        var next = SystemClock.elapsedRealtime()
        var sent = 0L
        var rttMs = 0L
        var hzT0 = SystemClock.elapsedRealtime()
        var hzN = 0
        var overSince = 0L
        var failStreak = 0
        var lastEmit = 0L
        var diagT0 = SystemClock.elapsedRealtime()
        var loopN = 0
        var postSum = 0L
        var maxPost = 0L

        while (currentCoroutineContext().isActive) {
            val now = SystemClock.elapsedRealtime()
            val s = settings

            // --- 读传感器 + 解算 ---
            val rv = tilt.relativeRotVecDeg()
            val hasNeutral = rv != null
            var rollRaw = 0f
            var pitchRaw = 0f
            var yawRaw = 0f
            if (rv != null) {
                // 握法决定哪根分量对应哪个动作。三根轴必须一起换，
                // 只换两根（早期版本就是这样）会让脚舵在竖握时对不上。
                if (s.swapAxes) {                       // 横握：屏幕朝上
                    rollRaw = rv[0]; pitchRaw = rv[1]; yawRaw = rv[2]
                } else {                                // 竖握：屏幕朝自己
                    pitchRaw = rv[0]; rollRaw = rv[2]; yawRaw = rv[1]
                }
            }

            // --- 掉手机保护 ---
            //
            // 超过这个角度就认为「不是在操纵，而是在重新握/掉了」。
            // 关键点：超限时**输出零**，而不是让曲线把它钳到满舵 ——
            // 曲线对超出量程的输入会 clamp 到 1.0，也就是满杆。用户只是
            // 把手机翻过来看一眼，飞机就会突然满舵横滚，这种事故比断线
            // 更难理解。钳位是数学上正确、操作上危险的行为。
            val limit = maxOf(55f, s.rangeDeg * 1.8f)
            val overLimit = abs(rollRaw) > limit || abs(pitchRaw) > limit
            if (overLimit) {
                if (overSince == 0L) overSince = now
                else if (now - overSince > OVER_LIMIT_MS && armed) {
                    armed = false
                    notice = "倾角过大，已自动上锁（手机是不是掉了？）"
                }
            } else {
                overSince = 0L
            }

            // 这里有两套值，必须分清：
            //
            //   **控制位置**（xPos/yPos/rPos）—— 手把杆推到了哪。杆位盘显示它。
            //   **指令值**（x/y/r）—— 实际发给飞机的东西。开了反转就和位置相反。
            //
            // 为什么盘子显示位置而不是指令：人对「拉杆」的直觉是位置，不是舵量。
            // 往后拉杆 = 手柄朝自己 = 屏幕上向下，同时机头抬起 —— 真机的驾驶杆
            // 也是这个关系。显示指令值的话，后仰会让点朝上、飞机抬头，看着像
            // 两件事各走各的。
            var xPos = curve(rollRaw, s.deadbandDeg, s.rangeDeg, s.expo)
            var yPos = curve(pitchRaw, s.deadbandDeg, s.rangeDeg, s.expo)
            val rt = rudderTouch
            // 脚舵有两个来源，优先级明确：手指按着滑块就以滑块为准，
            // 松开才回到「拧手机」。叠加会让用户搞不清到底谁在起作用。
            var rPos = when {
                rt != null -> rt
                s.rudderOn -> curve(yawRaw, s.rudderDeadbandDeg, s.rudderRangeDeg, s.expo)
                else -> 0f
            }
            if (overLimit) {
                // 超限时输出零，但位置照常显示 —— 让人看得见自己把手机举到哪了
                xPos = 0f; yPos = 0f
                if (rt == null) rPos = 0f
            }

            var x = if (s.invertX) -xPos else xPos
            var y = if (s.invertY) -yPos else yPos
            var r = if (s.invertRudder) -rPos else rPos

            // 叠加配平偏移，再整体夹到 ±1。
            //
            // 放在反转之后：配平量是「用户想要的输出」，不是「手的位置」，
            // 所以它得跟发送值同一边。
            //
            // 超限时 xPos/yPos 已经是 0，加完只剩配平量 —— 这正是想要的：
            // 用户转头看别处把手机举超了，姿态输入该被忽略，但已经配好的
            // 平飞状态不能跟着消失，否则飞机当场失去配平。
            x = (x + trimX).coerceIn(-1f, 1f)
            y = (y + trimY).coerceIn(-1f, 1f)
            lastOutX = x
            lastOutY = y

            val btnNow = effectiveButtons(now)
            val thrNow = if (s.throttleInvert) 1f - throttle else throttle

            // 未解锁一律发零。油门例外：它压根不发（字段缺失），
            // 让 DCS 保持自己那边的油门位置。
            // 视角：手机上是「按住拖哪算哪」，但发出去之前允许互换和翻转。
            // 互换是为了救 DCS 自动识别认错轴的场景（拖横的它认成 JOY_RY），
            // 那种情况重绑一遍很烦，换个开关就解决了。
            var vX = viewX
            var vY = viewY
            if (s.swapViewAxes) {
                val tmp = vX; vX = vY; vY = tmp
            }
            if (s.invertViewX) vX = -vX
            if (s.invertViewY) vY = -vY

            val sendX = if (armed) x else 0f
            val sendY = if (armed) y else 0f
            val sendR = if (armed) r else 0f
            val sendVX = if (armed) vX else 0f
            val sendVY = if (armed) vY else 0f
            val sendB = if (armed) btnNow else 0
            val sendT = if (armed && throttleTaken) thrNow else null

            // --- 发 ---
            val tt = SystemClock.elapsedRealtime()
            val res = post(sendX, sendY, sendR, sendVX, sendVY, sendT, sendB)
            val postMs = SystemClock.elapsedRealtime() - tt
            if (res >= 0) {
                rttMs = postMs
                vjoyFlag = res
                sent++
                hzN++
                failStreak = 0
                if (notice?.startsWith("发送失败") == true) notice = null
            } else {
                failStreak++
                // 连续 3 次才报错并上锁：单次抖动不该打断正在做的机动，
                // 但真断了必须立刻停手 —— 恢复瞬间满杆回弹会直接摔机
                if (failStreak >= 3) {
                    armed = false
                    notice = "发送失败，已自动上锁。检查 USB / adb reverse"
                }
            }

            // --- 发状态 ---
            // 50Hz 全量发给 Compose 会让整屏每 20ms 重组一次，白烧电。
            // 20Hz 对指针/数值来说已经完全跟手。
            val now2 = SystemClock.elapsedRealtime()
            if (now2 - lastEmit >= 50) {
                lastEmit = now2
                val hz = if (now2 - hzT0 >= 1000) hzN * 1000f / (now2 - hzT0) else -1f
                if (hz >= 0f) { hzT0 = now2; hzN = 0 }
                val prev = _state.value
                _state.value = prev.copy(
                    armed = armed,
                    sensorOk = tilt.available,
                    hasNeutral = hasNeutral,
                    ready = tilt.available && hasNeutral,
                    // 杆位盘显示**控制位置**（原始倾角），不是发给飞机的指令值。
                    // 后仰 → 点向下 → 机头抬起，和真机「拉杆」一致。
                    // 反转只影响 y 的符号，不影响这里的幅度，所以调死区/行程时
                    // 看它照样直观。
                    pitchDeg = pitchRaw,
                    rollDeg = rollRaw,
                    yawDeg = yawRaw,
                    x = sendX,
                    y = sendY,
                    r = sendR,
                    // 同样用控制位置，不是发送值
                    rudder = rPos,
                    vx = sendVX,
                    vy = sendVY,
                    trimX = trimX,
                    trimY = trimY,
                    throttle = throttle,
                    throttleTaken = throttleTaken,
                    buttons = sendB,
                    sent = sent,
                    hz = if (hz >= 0f) hz else prev.hz,
                    rttMs = rttMs,
                    vjoy = vjoyFlag,
                    notice = notice,
                )
            }

            // 定周期而不是「干完再 delay 20ms」：后者会把发送耗时算进周期，
            // 链路一慢频率就往下掉，越掉越慢
            next += periodMs
            val wait = next - SystemClock.elapsedRealtime()
            if (wait > 0) delay(wait) else next = SystemClock.elapsedRealtime()

            // 诊断：把「post 耗时」和「整圈耗时」分开打出来。频率不达标时
            // 这两条数一对比就知道该修网络还是修循环，不用猜。
            if (postMs > maxPost) maxPost = postMs
            postSum += postMs
            loopN++
            if (now2 - diagT0 >= 4000 && loopN > 0) {
                Log.i(
                    TAG,
                    "post 平均 ${postSum / loopN} ms / 峰值 $maxPost ms / 整圈 " +
                        "${(now2 - diagT0) / loopN} ms（${loopN} 次）│ " +
                        "传感器 ${tilt.ageMs} ms 前更新  rotvec=" +
                        (rv?.joinToString(",") { "%.1f".format(it) } ?: "未校零") +
                        "  x=${"%.2f".format(sendX)} y=${"%.2f".format(sendY)}" +
                        " r=${"%.2f".format(sendR)} t=${sendT ?: "-"}" +
                        " b=${sendB.toString(2)}  解锁=$armed  vJoy=$vjoyFlag" +
                        "  失败连击=$failStreak  提示=${notice ?: "-"}",
                )
                diagT0 = now2; loopN = 0; postSum = 0; maxPost = 0
            }
        }
    }

    // ------------------------------------------------------------ HTTP

    private val ch = HttpChannel(baseUrl)

    /** 见 HttpChannel 的注释：走裸 socket 是为了能设 TCP_NODELAY。 */
    private fun post(
        x: Float, y: Float, r: Float, vx: Float, vy: Float,
        t: Float?, b: Int,
    ): Int {
        val sb = StringBuilder(96)
        sb.append("{\"x\":").append(f(x))
        sb.append(",\"y\":").append(f(y))
        sb.append(",\"r\":").append(f(r))
        sb.append(",\"vx\":").append(f(vx))
        sb.append(",\"vy\":").append(f(vy))
        // 油门缺省 = 这次别管油门。见类注释里的「保持类通道」。
        if (t != null) sb.append(",\"t\":").append(f(t))
        sb.append(",\"b\":").append(b)
        sb.append('}')
        return ch.post(sb.toString().toByteArray(Charsets.US_ASCII))
    }

    /** 固定 3 位小数：够精确，且不会出现科学计数法。 */
    private fun f(v: Float): String = String.format(Locale.US, "%.3f", v)

    private companion object {
        const val TAG = "DcsPeripheral"
        const val BUTTON_COUNT = 16
        const val MIN_PULSE_MS = 120L

        /**
         * 超过倾角上限多久才真正上锁。
         *
         * 400ms 太短：把手上的手机从横握换到竖握、或者低头看一眼，都会
         * 短暂超过 55°，结果莫名其妙被锁。但也不能太长 —— 手机真掉了的
         * 时候，这段时间飞机是在无人操纵状态。1.2 秒是「够活人换姿势、
         * 不够让飞机飞走」的折中。超限期间输出为零，所以这段时间飞机
         * 只是杆回中，不会满舵乱滚。
         */
        const val OVER_LIMIT_MS = 1200L
    }
}

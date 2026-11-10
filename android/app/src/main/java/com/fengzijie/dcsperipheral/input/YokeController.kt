package com.fengzijie.dcsperipheral.input

import android.content.Context
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
import android.os.SystemClock
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
    val invertY: Boolean = false,
    /** 横握（配合横屏 UI）：左右倾斜绕的是设备长边，对应横滚。 */
    val swapAxes: Boolean = true,
)

data class YokeState(
    val armed: Boolean = false,
    val sensorOk: Boolean = false,
    val hasNeutral: Boolean = false,
    val ready: Boolean = false,
    /** 原始倾斜角（已按握法解算，未过曲线），给界面上的十字准星用 */
    val pitchDeg: Float = 0f,
    val rollDeg: Float = 0f,
    /** 实际发出去的量，-1..1 */
    val x: Float = 0f,
    val y: Float = 0f,
    val sent: Long = 0L,
    /** PC 端 vjoy_out.py 是否活着。false 时杆不会动，界面必须直说。 */
    val vjoyOk: Boolean = false,
    val hz: Float = 0f,
    val rttMs: Long = 0L,
    /** 非空表示原因，界面上直接显示 */
    val notice: String? = null,
)

/**
 * 把倾斜变成 vJoy 轴，并推给 PC。
 *
 * 三件事必须分开想，否则会写出「一卡全卡」的东西：
 *   1. 采传感器  —— 200Hz，在系统回调线程里，只做存四元数，绝不联网
 *   2. 算操纵量  —— 50Hz，在协程里，纯数学
 *   3. 发出去    —— 跟第 2 步同频，但可以失败、可以慢，失败了不能影响第 1 步
 *
 * 安全策略（这一段比功能重要）：
 *   - 默认**未解锁**。上电不会自己开始操纵飞机。
 *   - 网络一断立刻自动上锁。不能出现「链路恢复瞬间满杆回弹」——
 *     飞机会突然横滚，比失控更危险。
 *   - 倾角超过阈值持续 400ms 自动上锁。手机掉了/放桌上时，
 *     不能让飞机保持住那个舵量一直转。
 *   - PC 侧还有一道 500ms 看门狗兜底（vjoy_out.py），三层互不依赖。
 */
class YokeController(
    context: Context,
    private val baseUrl: String,
) {
    private val tilt = TiltSource(context.applicationContext)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val _state = MutableStateFlow(YokeState(sensorOk = tilt.available))
    val state: StateFlow<YokeState> = _state.asStateFlow()

    @Volatile var settings: YokeSettings = YokeSettings()
        private set

    @Volatile private var armed = false
    @Volatile private var vjoyOk = false
    @Volatile private var notice: String? = null
    private var job: Job? = null

    private val url = "${baseUrl.trimEnd('/')}/input"

    fun start() {
        if (job?.isActive == true) return
        tilt.start()
        job = scope.launch { loop() }
    }

    fun stop() {
        // 停之前一定回中并把「已上锁」的状态发出去，否则 PC 那边要等
        // 500ms 看门狗才回中，白白多一段时间的满杆
        armed = false
        runCatching { post(0f, 0f) }
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

    // ------------------------------------------------------------ 曲线

    /**
     * 死区 → 归一 → 曲线。
     *
     * 死区之后要**重新归一**（除以 range-deadband 而不是 range），
     * 否则死区边界上会有一个跳变：刚出死区就到 12% 杆量。
     * 这种小跳变在接近中位修正时特别难受。
     */
    private fun curve(raw: Float, s: YokeSettings): Float {
        val a = abs(raw)
        if (a <= s.deadbandDeg) return 0f
        val span = (s.rangeDeg - s.deadbandDeg).coerceAtLeast(1f)
        val v = ((a - s.deadbandDeg) / span).coerceAtMost(1f)
        // 经典 RC 指数曲线：(1-e)·v + e·v³。端点仍是 0 和 1，中间被压细
        val out = v * (1f - s.expo) + v * v * v * s.expo
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
            if (rv != null) {
                if (s.swapAxes) { rollRaw = rv[0]; pitchRaw = rv[1] }
                else { pitchRaw = rv[0]; rollRaw = rv[1] }
            }

            // --- 掉手机保护 ---
            val limit = maxOf(55f, s.rangeDeg * 1.8f)
            if (abs(rollRaw) > limit || abs(pitchRaw) > limit) {
                if (overSince == 0L) overSince = now
                else if (now - overSince > 400 && armed) {
                    armed = false
                    notice = "倾角过大，已自动上锁（手机是不是掉了？）"
                }
            } else {
                overSince = 0L
            }

            var x = curve(rollRaw, s)
            var y = curve(pitchRaw, s)
            if (s.invertX) x = -x
            if (s.invertY) y = -y

            // 未解锁就发精确的 0：不是「不发」。持续发 0 有两个用处 ——
            // PC 端看门狗不会误判为断线，界面也能靠 hz 反映链路活着。
            val sendX = if (armed) x else 0f
            val sendY = if (armed) y else 0f

            // --- 发 ---
            val tt = SystemClock.elapsedRealtime()
            val res = post(sendX, sendY)
            val postMs = SystemClock.elapsedRealtime() - tt
            if (res >= 0) {
                rttMs = postMs
                vjoyOk = res == 1
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
            // 20Hz 对准星来说已经完全跟手。
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
                    pitchDeg = pitchRaw,
                    rollDeg = rollRaw,
                    x = sendX,
                    y = sendY,
                    sent = sent,
                    hz = if (hz >= 0f) hz else prev.hz,
                    rttMs = rttMs,
                    vjoyOk = vjoyOk,
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
            if (now2 - diagT0 >= 2000 && loopN > 0) {
                Log.i(
                    TAG,
                    "post 平均 ${postSum / loopN} ms / 峰值 $maxPost ms / 整圈 " +
                        "${(now2 - diagT0) / loopN} ms（${loopN} 次）│ " +
                        "传感器 ${tilt.ageMs} ms 前更新  rotvec=" +
                        (rv?.joinToString(",") { "%.1f".format(it) } ?: "未校零") +
                        "  轴 x=${"%.2f".format(sendX)} y=${"%.2f".format(sendY)}" +
                        "  解锁=$armed  vJoy=$vjoyOk",
                )
                diagT0 = now2; loopN = 0; postSum = 0; maxPost = 0
            }
        }
    }

    // ------------------------------------------------------------ HTTP

    private val ch = HttpChannel(baseUrl)

    /** 见 HttpChannel 的注释：走裸 socket 是为了能设 TCP_NODELAY。 */
    private fun post(x: Float, y: Float): Int =
        ch.post("""{"x":${x},"y":${y}}""".toByteArray())

    private companion object {
        const val TAG = "DcsPeripheral"
    }
}

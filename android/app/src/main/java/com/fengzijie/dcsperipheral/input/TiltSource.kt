package com.fengzijie.dcsperipheral.input

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.SystemClock
import kotlin.math.abs
import kotlin.math.acos
import kotlin.math.sqrt

/**
 * 手机倾斜 → 三轴旋转向量（度）。
 *
 * 为什么用 TYPE_GAME_ROTATION_VECTOR 而不是 TYPE_ROTATION_VECTOR：
 *   后者融合了磁力计。室内磁环境很脏（机箱、音箱、桌面钢筋、耳机），
 *   典型症状是「手机放着不动，姿态自己慢慢转」。而我们只关心
 *   「相对刚才那个姿势偏了多少度」，根本不需要绝对方位 —— 用纯
 *   陀螺+加速度的 Game 版本更稳，也不用做 8 字校准。
 *   代价是有缓慢漂移，用一次「校零」就能消掉。
 *
 * 为什么算「相对旋转」而不是直接读欧拉角：
 *   欧拉角会万向节死锁，而且依赖「哪个轴是上」的约定，换个握法全乱。
 *   相对旋转向量没有这些问题：它就是「从校零姿态到当前姿态，绕哪根
 *   轴转了多少度」，轴和角都是确定的。
 */
class TiltSource(context: Context) : SensorEventListener {

    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val sensor: Sensor? = sm.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)

    @Volatile private var qNow: FloatArray? = null
    @Volatile private var qNeutral: FloatArray? = null
    @Volatile private var lastEventAt = 0L

    val available: Boolean get() = sensor != null
    val hasNeutral: Boolean get() = qNeutral != null

    /** 传感器多久没更新了。超过 200ms 基本可以认为被系统挂起或硬件抽风。 */
    val ageMs: Long
        get() = if (lastEventAt == 0L) Long.MAX_VALUE
        else SystemClock.elapsedRealtime() - lastEventAt

    fun start() {
        sensor?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME, 0) }
    }

    fun stop() {
        sm.unregisterListener(this)
    }

    /** 把「当前这一帧」记成中位。必须在收到过至少一帧之后调用。 */
    fun captureNeutral(): Boolean {
        val q = qNow ?: return false
        qNeutral = q.copyOf()
        return true
    }

    /** 忘掉中位（还没校过零时，任何读数都不该被当成操纵量发出去）。 */
    fun clearNeutral() {
        qNeutral = null
    }

    override fun onSensorChanged(e: SensorEvent) {
        if (e.values.size < 4) return
        val q = FloatArray(4)
        // 内置函数把旋转向量转成四元数，省得自己处理 sin(θ/2) 那一套
        SensorManager.getQuaternionFromVector(q, e.values)
        qNow = q
        lastEventAt = SystemClock.elapsedRealtime()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    /**
     * 相对于校零姿态的旋转向量，单位度。返回 `[绕设备X, 绕设备Y, 绕设备Z]`。
     *
     * 语义：如果把手机从校零姿势直接转到当前姿势，是「绕哪根轴、转多少度」。
     * 例如横屏托盘姿势下：
     *   - 绕设备 X（短边方向）→ 左右两端一高一低 = 横滚
     *   - 绕设备 Y（长边方向）→ 远近两边一高一低 = 俯仰
     * 具体取哪两个分量、正负怎么定，交给调用方（因为取决于握法）。
     *
     * 返回 null 表示还没校零，或者传感器还没出数据。
     */
    fun relativeRotVecDeg(): FloatArray? {
        val qn = qNeutral ?: return null
        val qc = qNow ?: return null
        return quatRelativeRotVecDeg(qn, qc)
    }
}

/**
 * 相对旋转向量（度）。从 [TiltSource] 里抽出来是为了能脱离 Android 单独验算。
 *
 * 数学上等价于：把「当前姿态」表示成「校零姿态」加一个旋转，取这个旋转的
 * 轴角形式（axis × angle）。因为四元数按 `qc = qn * q_local` 复合时，
 * `conj(qn) * qc` 恰好把 q_local 单独剥出来 —— 也就是**用户手持手机时
 * 手腕转的那个角度**，与手机当时朝向东南西北无关。
 *
 * 这一点很关键：如果换成 `qc = q_local * qn`（绕世界轴转），同一只手
 * 同一个动作，算出来会是一个混在两根轴上的斜向量，怎么调参数都调不直。
 */
internal fun quatRelativeRotVecDeg(qn: FloatArray, qc: FloatArray): FloatArray {
    // q_rel = conj(qn) * qc   —— 即 a = (qn.w, -qn.x, -qn.y, -qn.z) 与 qc 的哈密顿积
    //
    // 这几个符号必须照着 a=conj(qn) 展开，不能凭感觉写：
    // 写反任意两个，当 qn 是单位四元数时结果完全正确（那些项恰好乘 0），
    // 一旦斜着校零就会把「绕一根轴转」解成「两根轴各转一半」，而界面上
    // 只会表现为「杆斜着跑」，极难定位。
    var w = qn[0] * qc[0] + qn[1] * qc[1] + qn[2] * qc[2] + qn[3] * qc[3]
    var x = qn[0] * qc[1] - qn[1] * qc[0] - qn[2] * qc[3] + qn[3] * qc[2]
    var y = qn[0] * qc[2] + qn[1] * qc[3] - qn[2] * qc[0] - qn[3] * qc[1]
    var z = qn[0] * qc[3] - qn[1] * qc[2] + qn[2] * qc[1] - qn[3] * qc[0]

    // q 与 -q 表示同一个旋转。W 为负时取反，把角压回 0..π，
    // 否则 acos 会给出一个接近 360° 的等价大角，姿态判读直接崩。
    if (w < 0f) {
        w = -w; x = -x; y = -y; z = -z
    }
    w = w.coerceIn(-1f, 1f)

    val ang = 2.0 * acos(w.toDouble())
    // sin(ang/2) = sqrt(1 - w²)，就是**单位轴**的分母
    val s = sqrt((1.0 - w.toDouble() * w).coerceAtLeast(0.0))
    if (s < 1e-9 || abs(ang) < 1e-9) return floatArrayOf(0f, 0f, 0f)

    // 旋转向量 = 单位轴 × 角 = (x,y,z)/s × ang
    val k = Math.toDegrees(ang) / s
    return floatArrayOf((x * k).toFloat(), (y * k).toFloat(), (z * k).toFloat())
}

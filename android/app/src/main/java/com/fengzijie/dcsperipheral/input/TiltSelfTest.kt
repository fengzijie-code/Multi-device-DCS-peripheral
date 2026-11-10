package com.fengzijie.dcsperipheral.input

import android.util.Log
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 四元数解算的运行时自检。
 *
 * 为什么不做成单元测试：这个模块唯一的依赖是 Android 的 SensorManager，
 * 但真正需要验证的是纯数学。而把数学抽成纯函数以后，在真机上跑一遍
 * 反而更省事 —— 不用为了引 junit 去联网拉依赖，跑的就是发到手机上的
 * 那份字节码，不存在「测试通过了但编译产物不一样」的可能。
 *
 * 结果打到 logcat，tag = DcsPeripheral，用
 *     adb logcat -d -s DcsPeripheral
 * 看。
 */
object TiltSelfTest {

    private const val TAG = "DcsPeripheral"
    private const val TOL = 0.5f

    private fun qAxisAngle(ax: Float, ay: Float, az: Float, deg: Float): FloatArray {
        val n = sqrt(ax * ax + ay * ay + az * az)
        val h = Math.toRadians(deg.toDouble()) / 2.0
        val s = sin(h).toFloat()
        return floatArrayOf(cos(h).toFloat(), ax / n * s, ay / n * s, az / n * s)
    }

    /** (w,x,y,z) 哈密度积 */
    private fun qMul(a: FloatArray, b: FloatArray): FloatArray = floatArrayOf(
        a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
        a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
        a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
        a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
    )

    fun run() {
        val id = floatArrayOf(1f, 0f, 0f, 0f)
        var pass = 0
        var fail = 0

        fun check(name: String, qn: FloatArray, qc: FloatArray, want: FloatArray) {
            val got = quatRelativeRotVecDeg(qn, qc)
            val ok = (0..2).all { kotlin.math.abs(got[it] - want[it]) <= TOL }
            if (ok) pass++ else fail++
            Log.i(
                TAG,
                (if (ok) "PASS " else "FAIL ") + name +
                    "  得到 [" + "%.1f, %.1f, %.1f".format(got[0], got[1], got[2]) +
                    "]  期望 [" + "%.1f, %.1f, %.1f".format(want[0], want[1], want[2]) + "]",
            )
        }

        // 1. 没动过 → 零
        check("静止", id, id, floatArrayOf(0f, 0f, 0f))

        // 2. 绕三根轴各自纯转，必须只落在一个分量上
        check("绕X +20°", id, qAxisAngle(1f, 0f, 0f, 20f), floatArrayOf(20f, 0f, 0f))
        check("绕Y -15°", id, qAxisAngle(0f, 1f, 0f, -15f), floatArrayOf(0f, -15f, 0f))
        check("绕Z +40°", id, qAxisAngle(0f, 0f, 1f, 40f), floatArrayOf(0f, 0f, 40f))

        // 3. 关键用例：校零姿态不是单位四元数时，「手腕再转 20°」仍然要解出
        //    纯的 (20,0,0)。如果哪天把 q_rel 的乘序写反（conj(qc)*qn 或
        //    qc*conj(qn)），这一条会变成一个混在两根轴上的斜向量。
        val qn3 = qAxisAngle(0f, 0f, 1f, 45f)
        check("斜着校零后绕自身X +20°", qn3, qMul(qn3, qAxisAngle(1f, 0f, 0f, 20f)),
            floatArrayOf(20f, 0f, 0f))

        // 4. 随机一般轴：轴 (1,1,0)/√2 转 90°，分量应各为 63.64（=90/√2）
        check("斜轴 90°", id, qAxisAngle(1f, 1f, 0f, 90f), floatArrayOf(63.64f, 63.64f, 0f))

        // 5. q 与 -q 等价：同一姿态取反号，解算结果必须一样
        val qc5 = qAxisAngle(0f, 1f, 0f, 25f)
        check("q 取反号", id, floatArrayOf(-qc5[0], -qc5[1], -qc5[2], -qc5[3]),
            floatArrayOf(0f, 25f, 0f))

        // 6. 接近 180°：acos 在端点附近精度差，不能返回 NaN 或巨大的角
        val q180 = quatRelativeRotVecDeg(id, qAxisAngle(0f, 0f, 1f, 179f))
        val ok180 = q180.all { it.isFinite() } && kotlin.math.abs(q180[2] - 179f) <= 0.5f
        if (ok180) pass++ else fail++
        Log.i(TAG, (if (ok180) "PASS " else "FAIL ") + "179° 端点  [" +
            "%.1f, %.1f, %.1f".format(q180[0], q180[1], q180[2]) + "]")

        Log.i(TAG, "四元数自检完成：$pass 通过 / $fail 失败")
    }
}

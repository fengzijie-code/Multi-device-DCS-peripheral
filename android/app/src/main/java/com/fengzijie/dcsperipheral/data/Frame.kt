package com.fengzijie.dcsperipheral.data

import org.json.JSONObject

/**
 * 一帧遥测。
 *
 * 字段与 `dcs/Export.lua` 和 `tools/mock_export.py` 的输出一一对应。
 * P1 换成 protobuf 之后，这个类会变成生成代码，但字段名保持不变。
 *
 * 所有数值都做了有限性检查：DCS 会给出 NaN（地面状态、某些机型），
 * 直接喂给绘制会导致指针消失或崩溃，所以这里统一兜底成 0。
 */
data class Frame(
    val t: Double = 0.0,
    val alt: Double = 0.0,      // 海拔高度，米
    val agl: Double = 0.0,      // 无线电高度，米
    val ias: Double = 0.0,      // 指示空速，米/秒
    val gs: Double = 0.0,       // 真空速，米/秒
    val vs: Double = 0.0,       // 升降率，米/秒
    val pitch: Double = 0.0,    // 俯仰，弧度
    val bank: Double = 0.0,     // 滚转，弧度
    val hdg: Double = 0.0,      // 航向，弧度
    val g: Double = 1.0,        // 过载，G
    val mach: Double = 0.0,
    val dirty: Boolean = false, // 该帧被清洗过（含 NaN/Inf）
) {
    companion object {
        private fun num(o: JSONObject, key: String, fallback: Double = 0.0): Double {
            val v = o.optDouble(key, fallback)
            return if (v.isFinite()) v else fallback
        }

        fun from(o: JSONObject): Frame = Frame(
            t = num(o, "t"),
            alt = num(o, "alt"),
            agl = num(o, "agl"),
            ias = num(o, "ias"),
            gs = num(o, "gs"),
            vs = num(o, "vs"),
            pitch = num(o, "pitch"),
            bank = num(o, "bank"),
            hdg = num(o, "hdg"),
            g = num(o, "g", 1.0),
            mach = num(o, "mach"),
            dirty = o.optBoolean("dirty", false),
        )
    }

    // 显示用换算：DCS 玩家习惯用英尺 / 节 / 英尺每分钟
    val altFt: Double get() = alt * 3.28084
    val iasKt: Double get() = ias * 1.94384
    val vsFpm: Double get() = vs * 196.85
    val hdgDeg: Int get() = (((Math.toDegrees(hdg).toInt()) % 360) + 360) % 360
}

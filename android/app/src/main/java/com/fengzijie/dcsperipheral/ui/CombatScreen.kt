package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fengzijie.dcsperipheral.input.YokeState

/**
 * 战斗页 —— 交战那几秒钟要用的东西。
 *
 * 2026-11-14 改版：**视角已从手机端移除**（用户买了头瞄，看视角交给头瞄）。
 * 战斗页只剩交战必需项，版面：
 *
 *   油门 | 绿点盘(贴油门右侧) | 中间按钮区 | 机炮/武器(右上)
 *        | 脚舵 ————————————————————— 跨整宽，压在最底下
 *
 * 右上角一整组是「机炮 / 武器投放」两个发射键，都在右手拇指下，
 * 不用横跨屏幕找键。
 *
 * 绿点盘（杆位指示）留在油门右侧，雷达锁定 / 武器↑↓ / 干扰弹填进中间剩余空间。
 *
 * 发射拆成**机炮 / 武器投放**两个键：DCS 里 `Trigger`(机炮扳机) 和
 * `Weapon Release`(投放) 本来就是两条独立命令，旧版一个 BTN7 把两者混绑。
 * 编号不重排：BTN7 (`FIRE = 6`) 留给武器投放，机炮新增 BTN12 (`GUN_FIRE = 11`)；
 * 7..9 的预留位继续空着。详见 docs/BINDING.md 的迁移说明。
 *
 * 脚舵放最底下并跨整宽：它只在落地修正和狗斗压偏航时用，屏幕最下沿
 * 是拇指自然落点，而且横条越长分辨率越高。
 *
 * 右列下半的空位放**只读状态条**：这一页此前完全不显示链路 / vJoy 状态，
 * 交战中断链却看不出来比留白更糟；只读文字不抢触摸区。
 */
@Composable
fun CombatScreen(
    st: YokeState,
    rangeDeg: Float,
    onThrottle: (Float) -> Unit,
    onRudder: (Float) -> Unit,
    onRudderRelease: () -> Unit,
    onButtonDown: (Int) -> Unit,
    onButtonUp: (Int) -> Unit,
    onToggleArm: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        // ---------------- 主体：油门 / 绿点盘 / 中间按钮 / 右上操作组 ----------------
        Row(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            ThrottleStrip(
                value = st.throttle,
                taken = st.throttleTaken,
                armed = st.armed,
                onNudge = onThrottle,
                modifier = Modifier.width(62.dp).fillMaxHeight(),
            )

            // ---- 绿点指示：紧贴油门右侧，只占这一小块，不独占整行 ----
            // 尺寸跟着可用高度走，矮屏上也不会把脚舵挤出去。
            // 只显示、不响应触摸 —— 飞行中误触一个可交互区域太危险。
            Column(
                modifier = Modifier.width(150.dp).fillMaxHeight(),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                BoxWithConstraints(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentAlignment = Alignment.Center,
                ) {
                    val side = minOf(maxWidth, maxHeight).coerceAtMost(140.dp)
                    StickPad(
                        rollDeg = st.rollDeg,
                        pitchDeg = st.pitchDeg,
                        rudder = st.rudder,
                        rangeDeg = rangeDeg,
                        armed = st.armed,
                        modifier = Modifier.size(side),
                    )
                }
            }

            // ---- 中间：紧凑按钮组（20:57 用户嫌「校准/解锁 + 4 个按钮」太大） ----
            // 旧版 4 个按钮用 weight(1f) 各撑半屏宽、约 130dp 高，解锁键还
            // fillMaxWidth 横跨整列。现在全部收成固定尺寸、2x2 居中：
            // 解锁 220x42dp，四个按钮各 132x60dp。省下来的空间留白，
            // 不再用「撑满」冒充「好用」—— 中间这块本来就该让人一眼扫完。
            Box(
                modifier = Modifier.weight(1f).fillMaxHeight(),
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    ArmButton(
                        armed = st.armed,
                        ready = st.ready,
                        onClick = onToggleArm,
                        modifier = Modifier.width(220.dp),
                        height = 42.dp,
                    )
                    Spacer(Modifier.height(4.dp))

                    // 武器上下并排：一对操作，拇指在同一高度左右蹭就能盲切。
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        GuardButton(
                            text = "武器 ↑",
                            enabled = st.armed,
                            guardMs = 150,
                            onDown = { onButtonDown(YokeBtn.WEAPON_PREV) },
                            onUp = { onButtonUp(YokeBtn.WEAPON_PREV) },
                            modifier = Modifier.width(132.dp).height(60.dp),
                        )
                        GuardButton(
                            text = "武器 ↓",
                            enabled = st.armed,
                            guardMs = 150,
                            onDown = { onButtonDown(YokeBtn.WEAPON_NEXT) },
                            onUp = { onButtonUp(YokeBtn.WEAPON_NEXT) },
                            modifier = Modifier.width(132.dp).height(60.dp),
                        )
                    }

                    // 雷达锁定 / 干扰弹并排。干扰弹保持琥珀，红色全给发射键。
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        GuardButton(
                            text = "锁定",
                            sub = "雷达锁定目标",
                            enabled = st.armed,
                            guardMs = 150,
                            onDown = { onButtonDown(YokeBtn.LOCK) },
                            onUp = { onButtonUp(YokeBtn.LOCK) },
                            modifier = Modifier.width(132.dp).height(60.dp),
                        )
                        GuardButton(
                            text = "干扰弹",
                            sub = "投放",
                            enabled = st.armed,
                            guardMs = 150,
                            onDown = { onButtonDown(YokeBtn.COUNTERMEASURE) },
                            onUp = { onButtonUp(YokeBtn.COUNTERMEASURE) },
                            modifier = Modifier.width(132.dp).height(60.dp),
                        )
                    }
                }
                // 状态条挪到这里：右列发射键占满后，中间留白处刚好够放一行小字。
                // 中间这块有留白，合并成一行小字足够，也不抢任何触摸区。
                Text(
                    text = st.notice ?: ("链路 ${st.rttMs} ms · ${fmt1(st.hz)} Hz · " + when (st.vjoy) {
                        1 -> "摇杆就绪"
                        2 -> "摇杆缺轴"
                        else -> "摇杆未运行"
                    }),
                    color = if (st.notice != null || st.vjoy != 1) Ink.Amber else Ink.Dim,
                    fontSize = 10.sp,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }

            // ---- 右上角操作组：机炮 / 武器，全部在右手拇指下 ----
            // 视角已移除：用户买了头瞄，看视角交给头瞄（见 docs/HANDOFF.md）。
            Column(
                modifier = Modifier.width(220.dp).fillMaxHeight(),
                verticalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                // 发射两键：左上机炮 / 右上武器投放。
                // 两个都是不可逆动作，所以都吃 250ms 长按门槛、都用红色。
                Row(
                    modifier = Modifier.fillMaxWidth().height(84.dp),
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    GuardButton(
                        text = "机炮",
                        sub = "扳机",
                        enabled = st.armed,
                        guardMs = 250,
                        danger = true,
                        textSp = 18f,
                        subSp = 12f,
                        onDown = { onButtonDown(YokeBtn.GUN_FIRE) },
                        onUp = { onButtonUp(YokeBtn.GUN_FIRE) },
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                    )
                    GuardButton(
                        text = "武器",
                        sub = "投放",
                        enabled = st.armed,
                        guardMs = 250,
                        danger = true,
                        textSp = 18f,
                        subSp = 12f,
                        onDown = { onButtonDown(YokeBtn.FIRE) },
                        onUp = { onButtonUp(YokeBtn.FIRE) },
                        modifier = Modifier.weight(1f).fillMaxHeight(),
                    )
                }

                // 剩下的一点点高度留白：和脚舵隔开，免得拇指顺着发射键滑到脚舵。
                // 状态条已挪到中间留白处（右列放大后这里塞不下两行字）。
                Spacer(Modifier.weight(1f).fillMaxWidth())
            }
        }

        // ---------------- 最底下：脚舵，跨整宽 ----------------
        // 和起降页同一条实心滑块，能一直压住。按住时以它为准，
        // 松开交还给「拧手机」，两者不叠加。
        Row(
            modifier = Modifier.fillMaxWidth().height(34.dp),
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
    }
}

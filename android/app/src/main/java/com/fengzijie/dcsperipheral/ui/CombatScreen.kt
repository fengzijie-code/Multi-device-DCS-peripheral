package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fengzijie.dcsperipheral.input.YokeState

/**
 * 战斗页 —— 只留下交战那几秒钟要用的东西。
 *
 * 版面思路和飞行页一致，按「离手多远」排：油门贴左边缘（左拇指），
 * 杆位块居中（只显示，不用碰），操作按钮全在右列（右拇指一列按下去）。
 *
 * 为什么按钮竖排四个而不是做成一个方向圆块：
 *   圆块要靠「相对滑动」操作，手指得先摸到起点、再确认方向，全程需要看屏幕。
 *   竖排按钮位置固定，拇指从下往上摸一遍就记住了，闭着眼也能按对。
 *   交战时眼睛在目标和 HUD 上，不该分给手机。
 *
 * 顺序也是刻意的：发射在最下（拇指最自然的位置），锁定在它上面，
 * 切武器在最上（最不常用、误触代价最小）。误触切武器只是换弹种，
 * 误触发射是不可逆的。
 */
@Composable
fun CombatScreen(
    st: YokeState,
    rangeDeg: Float,
    onThrottle: (Float) -> Unit,
    onButtonDown: (Int) -> Unit,
    onButtonUp: (Int) -> Unit,
    onToggleArm: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxSize(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        ThrottleStrip(
            value = st.throttle,
            taken = st.throttleTaken,
            armed = st.armed,
            onNudge = onThrottle,
            modifier = Modifier.width(62.dp).fillMaxHeight(),
        )

        StickPad(
            rollDeg = st.rollDeg,
            pitchDeg = st.pitchDeg,
            rudder = st.rudder,
            rangeDeg = rangeDeg,
            armed = st.armed,
            modifier = Modifier.weight(1f).fillMaxHeight(),
        )

        Column(
            Modifier.width(196.dp).fillMaxHeight(),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            ArmButton(armed = st.armed, ready = st.ready, onClick = onToggleArm)
            Spacer(Modifier.height(0.dp))

            GuardButton(
                text = "武器 ↑",
                sub = "上一个",
                enabled = st.armed,
                guardMs = 150,
                onDown = { onButtonDown(YokeBtn.WEAPON_PREV) },
                onUp = { onButtonUp(YokeBtn.WEAPON_PREV) },
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            GuardButton(
                text = "武器 ↓",
                sub = "下一个",
                enabled = st.armed,
                guardMs = 150,
                onDown = { onButtonDown(YokeBtn.WEAPON_NEXT) },
                onUp = { onButtonUp(YokeBtn.WEAPON_NEXT) },
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            GuardButton(
                text = "锁定",
                sub = "雷达锁定目标",
                enabled = st.armed,
                guardMs = 150,
                onDown = { onButtonDown(YokeBtn.LOCK) },
                onUp = { onButtonUp(YokeBtn.LOCK) },
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            GuardButton(
                text = "发射",
                sub = "按住生效",
                enabled = st.armed,
                guardMs = 250,
                danger = true,
                onDown = { onButtonDown(YokeBtn.FIRE) },
                onUp = { onButtonUp(YokeBtn.FIRE) },
                modifier = Modifier.fillMaxWidth().weight(1.2f),
            )
        }
    }
}

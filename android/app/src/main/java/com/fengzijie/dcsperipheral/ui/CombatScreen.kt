package com.fengzijie.dcsperipheral.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
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

        // 杆位块固定 160dp 居中，不再撑满整列。
        // 战斗中它的作用是「瞥一眼确认杆在哪」，不是精确读数 ——
        // 撑满会把右列的按钮挤到边上，而按钮才是这个页面真正要用的东西。
        Box(
            Modifier.weight(1f).fillMaxHeight(),
            contentAlignment = Alignment.Center,
        ) {
            StickPad(
                rollDeg = st.rollDeg,
                pitchDeg = st.pitchDeg,
                rudder = st.rudder,
                rangeDeg = rangeDeg,
                armed = st.armed,
                modifier = Modifier.size(160.dp),
            )
        }

        Column(
            Modifier.width(196.dp).fillMaxHeight(),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            ArmButton(armed = st.armed, ready = st.ready, onClick = onToggleArm)

            // 武器上下并排：它们是一对，并排比竖排更容易「盲切」——
            // 拇指在同一个高度左右蹭，不用上下找位置。
            Row(
                Modifier.fillMaxWidth().weight(0.9f),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                GuardButton(
                    text = "武器 ↑",
                    enabled = st.armed,
                    guardMs = 150,
                    onDown = { onButtonDown(YokeBtn.WEAPON_PREV) },
                    onUp = { onButtonUp(YokeBtn.WEAPON_PREV) },
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                )
                GuardButton(
                    text = "武器 ↓",
                    enabled = st.armed,
                    guardMs = 150,
                    onDown = { onButtonDown(YokeBtn.WEAPON_NEXT) },
                    onUp = { onButtonUp(YokeBtn.WEAPON_NEXT) },
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                )
            }

            GuardButton(
                text = "锁定",
                sub = "雷达锁定目标",
                enabled = st.armed,
                guardMs = 150,
                onDown = { onButtonDown(YokeBtn.LOCK) },
                onUp = { onButtonUp(YokeBtn.LOCK) },
                modifier = Modifier.fillMaxWidth().weight(1f),
            )
            // 干扰弹放在锁定和发射之间：被锁定时拇指从锁定往下滑一格就到，
            // 而且和发射拉开一格距离 —— 这两个按错的代价完全不同。
            // 颜色用琥珀不用红：红色已经被发射占了，混用会让人在急的时候按错。
            GuardButton(
                text = "干扰弹",
                sub = "投放",
                enabled = st.armed,
                guardMs = 150,
                onDown = { onButtonDown(YokeBtn.COUNTERMEASURE) },
                onUp = { onButtonUp(YokeBtn.COUNTERMEASURE) },
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

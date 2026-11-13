package com.fengzijie.dcsperipheral

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.fengzijie.dcsperipheral.data.Frame
import com.fengzijie.dcsperipheral.input.TiltSelfTest
import com.fengzijie.dcsperipheral.input.YokeController
import com.fengzijie.dcsperipheral.input.YokeSettings
import com.fengzijie.dcsperipheral.input.YokeState
import com.fengzijie.dcsperipheral.net.BridgePoller
import com.fengzijie.dcsperipheral.net.LinkEvent
import com.fengzijie.dcsperipheral.ui.AttitudeIndicator
import com.fengzijie.dcsperipheral.ui.CalibScreen
import com.fengzijie.dcsperipheral.ui.CombatScreen
import com.fengzijie.dcsperipheral.ui.DcsTheme
import com.fengzijie.dcsperipheral.ui.HeadingTape
import com.fengzijie.dcsperipheral.ui.Ink
import com.fengzijie.dcsperipheral.ui.VerticalTape
import com.fengzijie.dcsperipheral.ui.YokeScreen
import kotlinx.coroutines.flow.MutableStateFlow
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // 四元数解算没法靠眼睛验：跑一遍自检打 logcat，几微秒的事
        TiltSelfTest.run()
        setContent {
            DcsTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    Root()
                }
            }
        }
    }
}

private fun fmt(v: Double, decimals: Int = 0, signed: Boolean = false): String {
    if (!v.isFinite()) return "--"
    val spec = if (signed) "%+.${decimals}f" else "%.${decimals}f"
    return String.format(Locale.US, spec, v)
}

@Composable
private fun Root() {
    val ctx = LocalContext.current
    val prefs = remember { ctx.getSharedPreferences("dcs_peripheral", Context.MODE_PRIVATE) }

    var server by remember { mutableStateOf(prefs.getString("server", "") ?: "") }
    var showSetup by remember { mutableStateOf(server.isBlank()) }
    // 记住上次停在哪一页：切到摇杆页后被系统回收，回来不该又跳回仪表
    var mode by remember { mutableStateOf(prefs.getString("mode", "pfd") ?: "pfd") }
    var yset by remember { mutableStateOf(loadYokeSettings(prefs)) }

    var frame by remember { mutableStateOf(Frame()) }
    var hasData by remember { mutableStateOf(false) }
    var connected by remember { mutableStateOf(false) }
    var rtt by remember { mutableStateOf(0L) }
    var hz by remember { mutableStateOf(0.0) }
    var status by remember { mutableStateOf("未设置服务器") }
    var errMsg by remember { mutableStateOf("") }

    LaunchedEffect(server) {
        if (server.isBlank()) {
            status = "未设置服务器"
            return@LaunchedEffect
        }
        BridgePoller(ctx, server).events().collect { ev ->
            when (ev) {
                is LinkEvent.Connecting -> {
                    status = "连接中"
                    errMsg = ""
                }
                is LinkEvent.Ok -> {
                    rtt = ev.rttMs
                    hz = ev.hz
                    hasData = ev.hasData
                    ev.frame?.let { frame = it }
                    connected = true
                    status = if (ev.hasData) "已连接" else "等待遥测"
                    errMsg = ""
                }
                is LinkEvent.Error -> {
                    // 断开时不能继续把旧数字当实时数据显示 —— 飞行仪表上这是危险行为
                    connected = false
                    status = "连接失败"
                    errMsg = ev.message
                }
            }
        }
    }

    // ---------------------------------------------------------------- 摇杆
    val ctl = remember(server) {
        if (server.isBlank()) null else YokeController(ctx, server)
    }
    val emptyFlow = remember { MutableStateFlow(YokeState()) }
    val yokeSt by (ctl?.state ?: emptyFlow).collectAsState()

    DisposableEffect(ctl) {
        ctl?.updateSettings(yset)
        onDispose { ctl?.shutdown() }
    }

    // 换了服务器地址会造出一个新的 controller，这时必须把「解锁」状态丢掉 ——
    // 不能让新链路上电就是满杆
    LaunchedEffect(mode, ctl) {
        val live = mode == "yoke" || mode == "calib" || mode == "combat"
        if (live && ctl != null) ctl.start() else ctl?.stop()
    }

    // 摇杆/校准/战斗页要一直亮屏：手握着手机看杆位，屏幕灭掉等于失控
    val view = LocalView.current
    DisposableEffect(view, mode) {
        view.keepScreenOn = (mode == "yoke" || mode == "calib" || mode == "combat")
        onDispose { view.keepScreenOn = false }
    }

    // 退到后台立刻停手。系统会限流后台传感器，这时候还挂着解锁状态
    // 却收不到新姿态 = 保持住最后一帧的舵量，是最坏的情况。
    val activity = ctx as? androidx.activity.ComponentActivity
    DisposableEffect(activity, ctl) {
        val obs = LifecycleEventObserver { _, ev ->
            if (ev == Lifecycle.Event.ON_PAUSE) ctl?.stop()
        }
        activity?.lifecycle?.addObserver(obs)
        onDispose { activity?.lifecycle?.removeObserver(obs) }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .padding(horizontal = 8.dp, vertical = 6.dp),
    ) {
        Header(
            status = status,
            server = server,
            dirty = frame.dirty,
            mode = mode,
            yokeArmed = yokeSt.armed,
            onMode = {
                mode = it
                prefs.edit().putString("mode", it).apply()
            },
            onSetup = { showSetup = true },
        )

        Spacer(Modifier.height(6.dp))

        if (mode == "yoke" || mode == "calib" || mode == "combat") {
            if (server.isBlank()) {
                EmptyHint(
                    "先设置服务器地址，摇杆才有地方发数据",
                    Modifier.fillMaxWidth().weight(1f),
                )
            } else if (mode == "combat") {
                CombatScreen(
                    st = yokeSt,
                    rangeDeg = yset.rangeDeg,
                    onThrottle = { ctl?.nudgeThrottle(it) },
                    onRudder = { ctl?.setRudder(it) },
                    onRudderRelease = { ctl?.releaseRudder() },
                    onButtonDown = { ctl?.pressButton(it) },
                    onButtonUp = { ctl?.releaseButton(it) },
                    onToggleArm = { ctl?.toggleArmed() },
                    modifier = Modifier.fillMaxWidth().weight(1f),
                )
            } else if (mode == "yoke") {
                YokeScreen(
                    st = yokeSt,
                    set = yset,
                    onThrottle = { ctl?.nudgeThrottle(it) },
                    onRudder = { ctl?.setRudder(it) },
                    onRudderRelease = { ctl?.releaseRudder() },
                    onButtonDown = { ctl?.pressButton(it) },
                    onButtonUp = { ctl?.releaseButton(it) },
                    onToggleArm = { ctl?.toggleArmed() },
                    onCalibrate = { ctl?.captureNeutral() },
                    onSettings = {
                        mode = "calib"
                        prefs.edit().putString("mode", "calib").apply()
                    },
                    onTrimCapture = { ctl?.captureTrim() },
                    onTrimClear = { ctl?.clearTrim() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                )
            } else {
                CalibScreen(
                    st = yokeSt,
                    set = yset,
                    onSettings = { ns ->
                        yset = ns
                        saveYokeSettings(prefs, ns)
                        ctl?.updateSettings(ns)
                    },
                    onCalibrate = { ctl?.captureNeutral() },
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                )
            }
        } else {
            // 断线时整块读数区压暗：旧数字停在那里看起来和实时数据一模一样，
            // 在飞行中这是危险的。必须让人一眼看出「这不是当前姿态」。
            val dataAlpha = if (connected) 1f else 0.18f

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center,
            ) {
                Row(
                    modifier = Modifier.fillMaxSize(),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    // 左速度、右高度（用户习惯）
                    VerticalTape(
                        value = frame.iasKt,
                        range = 60.0,
                        minorStep = 10.0,
                        labelStep = 20.0,
                        unit = "kt",
                        alignEnd = true,
                        modifier = Modifier
                            .width(80.dp)
                            .fillMaxHeight()
                            .alpha(dataAlpha),
                    )

                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .alpha(dataAlpha),
                    ) {
                        AttitudeIndicator(
                            pitchRad = frame.pitch,
                            bankRad = frame.bank,
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f),
                        )
                        Spacer(Modifier.height(4.dp))
                        HeadingTape(
                            headingDeg = frame.hdgDegF,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(32.dp),
                        )
                    }

                    VerticalTape(
                        value = frame.altFt,
                        range = 1000.0,
                        minorStep = 100.0,
                        labelStep = 200.0,
                        unit = "ft",
                        alignEnd = false,
                        modifier = Modifier
                            .width(80.dp)
                            .fillMaxHeight()
                            .alpha(dataAlpha),
                    )
                }

                if (!connected) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .background(Color(0xE6101216), RoundedCornerShape(12.dp))
                            .padding(horizontal = 18.dp, vertical = 10.dp),
                    ) {
                        Text(
                            text = if (hasData) "数据已冻结" else "尚未收到数据",
                            color = Ink.Red,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Medium,
                        )
                        Spacer(Modifier.height(3.dp))
                        Text(
                            text = errMsg.ifBlank { "正在重连…" },
                            color = Ink.Dim,
                            fontSize = 11.sp,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }

            Spacer(Modifier.height(6.dp))

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .alpha(dataAlpha),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Tile("VS", fmt(frame.vsFpm, 0, signed = true), "fpm", Modifier.weight(1f))
                Tile("G", fmt(frame.g, 1), "g", Modifier.weight(1f))
                Tile("AOA", fmt(frame.aoaDeg, 0), "°", Modifier.weight(1f))
                Tile("MACH", fmt(frame.mach, 2), "", Modifier.weight(1f))
            }

            Spacer(Modifier.height(6.dp))

            Footer(status = status, rtt = rtt, hz = hz, err = errMsg, server = server)
        }
    }

    if (showSetup) {
        SetupDialog(
            initial = server,
            onDismiss = { showSetup = false },
            onConfirm = { value ->
                val cleaned = value.trim().trimEnd('/')
                server = cleaned
                prefs.edit().putString("server", cleaned).apply()
                showSetup = false
            },
        )
    }
}

@Composable
private fun EmptyHint(text: String, modifier: Modifier = Modifier) {
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Text(text, color = Ink.Dim, fontSize = 13.sp)
    }
}

/**
 * 参数存储版本。
 *
 * 为什么需要它：`loadYokeSettings` 读的是 SharedPreferences，只要某个键已经
 * 存在，改代码里的默认值就**不会生效**。实测发现俯仰和油门方向相反，光把
 * 默认值改成 true 对已经装过的机器没用，必须显式迁移一次。
 */
private const val SETTINGS_VER = 3

private fun loadYokeSettings(p: android.content.SharedPreferences): YokeSettings {
    if (p.getInt("yk_ver", 1) < 2) {
        // v2：俯仰与油门在 DCS 里方向相反，默认翻过来。
        // 只覆盖这两项，其他偏好原样保留。
        p.edit()
            .putBoolean("yk_invy", true)
            .putBoolean("yk_thr_inv", true)
            .putInt("yk_ver", SETTINGS_VER)
            .apply()
    }
    if (p.getInt("yk_ver", 1) < 3) {
        // v3：视角轴整体移除（用户买了头瞄）。清掉旧的视角偏好，避免残留。
        p.edit()
            .remove("yk_view_swap")
            .remove("yk_view_invx")
            .remove("yk_view_invy")
            .putInt("yk_ver", SETTINGS_VER)
            .apply()
    }
    return YokeSettings(
        deadbandDeg = p.getFloat("yk_deadband", 2.5f),
        rangeDeg = p.getFloat("yk_range", 22f),
        expo = p.getFloat("yk_expo", 0.35f),
        invertX = p.getBoolean("yk_invx", false),
        invertY = p.getBoolean("yk_invy", true),
        swapAxes = p.getBoolean("yk_swap", true),
        rudderOn = p.getBoolean("yk_rudder_on", true),
        rudderDeadbandDeg = p.getFloat("yk_rudder_db", 4f),
        rudderRangeDeg = p.getFloat("yk_rudder_range", 28f),
        invertRudder = p.getBoolean("yk_rudder_inv", false),
        throttleInvert = p.getBoolean("yk_thr_inv", true),
        // 默认关：飞固定翼是主场景，配平按钮在那里没用还占地方
        trimOn = p.getBoolean("yk_trim_on", false),
    )
}

private fun saveYokeSettings(p: android.content.SharedPreferences, s: YokeSettings) {
    p.edit()
        .putFloat("yk_deadband", s.deadbandDeg)
        .putFloat("yk_range", s.rangeDeg)
        .putFloat("yk_expo", s.expo)
        .putBoolean("yk_invx", s.invertX)
        .putBoolean("yk_invy", s.invertY)
        .putBoolean("yk_swap", s.swapAxes)
        .putBoolean("yk_rudder_on", s.rudderOn)
        .putFloat("yk_rudder_db", s.rudderDeadbandDeg)
        .putFloat("yk_rudder_range", s.rudderRangeDeg)
        .putBoolean("yk_rudder_inv", s.invertRudder)
        .putBoolean("yk_thr_inv", s.throttleInvert)
        .putBoolean("yk_trim_on", s.trimOn)
        .apply()
}

@Composable
private fun Header(
    status: String,
    server: String,
    dirty: Boolean,
    mode: String,
    yokeArmed: Boolean,
    onMode: (String) -> Unit,
    onSetup: () -> Unit,
) {
    val dotColor = when {
        status == "已连接" -> Ink.Teal
        status == "等待遥测" || status == "连接中" -> Ink.Amber
        else -> Ink.Red
    }
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(9.dp)
                .background(dotColor, CircleShape)
        )
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = "DCS 外设 · v1.3.6",
                color = Ink.Fg,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
            )
            Text(
                text = if (server.isBlank()) "未设置服务器地址" else server,
                color = Ink.Dim,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
        if (dirty) {
            Text(
                text = "脏数据",
                color = Ink.Amber,
                fontSize = 11.sp,
                modifier = Modifier.padding(end = 8.dp),
            )
        }
        ModeTab("仪表", on = mode == "pfd", onClick = { onMode("pfd") })
        Spacer(Modifier.width(4.dp))
        // 起降和战斗共用同一套控制器和同一个 ARM 状态，只是版面不同：
        // 起降要脚舵/襟翼/起落架，战斗只要武器和发射（视角已交给头瞄）。
        ModeTab("起降", on = mode == "yoke", armed = yokeArmed, onClick = { onMode("yoke") })
        Spacer(Modifier.width(4.dp))
        ModeTab("战斗", on = mode == "combat", armed = yokeArmed, onClick = { onMode("combat") })
        Spacer(Modifier.width(4.dp))
        ModeTab("校准", on = mode == "calib", onClick = { onMode("calib") })
        Spacer(Modifier.width(6.dp))
        TextButton(onClick = onSetup) {
            Text("设置", color = Ink.Fg, fontSize = 13.sp)
        }
    }
}

/** 顶部的页面切换。摇杆页在解锁时左边会亮一个红点，人在仪表页也能看见。 */
@Composable
private fun ModeTab(
    text: String,
    on: Boolean,
    armed: Boolean = false,
    onClick: () -> Unit,
) {
    val line = when {
        armed -> Ink.Red
        on -> Ink.Teal.copy(alpha = 0.7f)
        else -> Ink.Line
    }
    val fg = when {
        armed -> Ink.Red
        on -> Ink.Teal
        else -> Ink.Dim
    }
    Box(
        modifier = Modifier
            .height(30.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(if (on) Ink.Teal.copy(alpha = 0.14f) else Ink.Surface)
            .border(1.dp, line, RoundedCornerShape(8.dp))
            .clickable { onClick() }
            .padding(horizontal = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = fg, fontSize = 12.sp, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun Tile(label: String, value: String, unit: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .background(Ink.Surface, RoundedCornerShape(10.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp),
    ) {
        Text(label, color = Ink.Dim, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                text = value,
                color = Ink.Fg,
                fontSize = 20.sp,
                fontWeight = FontWeight.Medium,
                fontFamily = FontFamily.Monospace,
                maxLines = 1,
                softWrap = false,
            )
            if (unit.isNotEmpty()) {
                Text(
                    text = unit,
                    color = Ink.Dim,
                    fontSize = 10.sp,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.padding(start = 3.dp, bottom = 3.dp),
                )
            }
        }
    }
}

@Composable
private fun Footer(status: String, rtt: Long, hz: Double, err: String, server: String) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = "RTT ${rtt} ms",
                color = if (rtt in 1..120) Ink.Dim else Ink.Amber,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text = "上游 ${fmt(hz, 1)} Hz",
                color = Ink.Dim,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
            Text(
                text = status,
                color = if (status == "已连接") Ink.Teal else Ink.Amber,
                fontSize = 11.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
        if (err.isNotEmpty()) {
            Text(
                text = err,
                color = Ink.Red,
                fontSize = 11.sp,
                modifier = Modifier.padding(top = 3.dp),
            )
            // USB 通道最常见的故障是 adb 服务重启后反向转发丢失。
            // 这个提示能省掉「到底是服务没起、防火墙、还是转发掉了」的排查。
            if (server.contains("127.0.0.1") || server.contains("localhost")) {
                Text(
                    text = "USB 通道：请在 PC 上重新执行 adb reverse tcp:8080 tcp:8080",
                    color = Ink.Dim,
                    fontSize = 10.sp,
                    modifier = Modifier.padding(top = 1.dp),
                )
            }
        }
    }
}

@Composable
private fun SetupDialog(
    initial: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    // 默认填 USB 通道的地址：配合 PC 上的 `adb reverse tcp:8080 tcp:8080`，
    // 手机上的 127.0.0.1:8080 会被转发到 PC 的 8080，延迟 2–4ms，不依赖任何网络。
    var text by remember {
        mutableStateOf(initial.ifBlank { "http://127.0.0.1:8080" })
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("桥接服务地址", color = Ink.Fg, fontSize = 16.sp) },
        text = {
            Column {
                Text(
                    text = "填 PC 上信标/桥接的地址。跑 netprobe.py 可以看到候选 IP。",
                    color = Ink.Dim,
                    fontSize = 12.sp,
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    singleLine = true,
                    label = { Text("http://IP:端口") },
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(text) }) { Text("连接") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("取消", color = Ink.Dim) }
        },
        containerColor = Ink.Surface,
    )
}

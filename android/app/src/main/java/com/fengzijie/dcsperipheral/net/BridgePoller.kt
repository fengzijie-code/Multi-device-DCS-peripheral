package com.fengzijie.dcsperipheral.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import com.fengzijie.dcsperipheral.data.Frame
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

sealed interface LinkEvent {
    data object Connecting : LinkEvent

    data class Ok(
        val frame: Frame?,
        val rttMs: Long,
        val hz: Double,
        val hasData: Boolean,
    ) : LinkEvent

    data class Error(val message: String) : LinkEvent
}

/**
 * P0 阶段的桥接客户端：HTTP 轮询。
 *
 * 为什么先轮询而不是 WebSocket/QUIC：
 * P0 只需要证明「网络通 + 数据能显示」，轮询在这个阶段足够，
 * 而且不引入额外依赖，构建失败的几率最低。
 * P1 会换成 QUIC 长连接，届时 deltas 可以做到 60Hz 不重传。
 *
 * ## 关键：必须把进程绑定到 Wi-Fi 网络
 *
 * 这是实测踩出来的坑。当 PC 开热点时，这个热点**没有互联网**，
 * Android 会把它标记为 unvalidated，并把蜂窝保持为默认网络。
 * 此时普通 socket 发往 192.168.137.1 的包会走**蜂窝**接口
 * （实测源地址是 10.153.183.186），永远到不了 PC。
 *
 * `bindProcessToNetwork(wifi)` 强制本进程后续新建的 socket 走 Wi-Fi，
 * 问题消失。这不是权宜之计 —— 任何「直连局域网设备」的场景都会遇到，
 * 所以它属于产品逻辑，不是 workaround。
 *
 * 只在目标是私有地址时才绑定：走 Tailscale / 公网时不该干预系统选择。
 */
class BridgePoller(
    private val context: Context,
    private val baseUrl: String,
    private val intervalMs: Long = 100,
) {
    private var pinnedToWifi = false
    private var wifiLock: WifiManager.WifiLock? = null

    fun events(): Flow<LinkEvent> = flow {
        bindToTargetNetwork()
        try {
            emit(LinkEvent.Connecting)
            var consecutiveFails = 0
            while (true) {
                val t0 = System.nanoTime()
                try {
                    val text = fetch("$baseUrl/state")
                    val rtt = (System.nanoTime() - t0) / 1_000_000
                    val o = JSONObject(text)
                    val frame = o.optJSONObject("frame")?.let { Frame.from(it) }
                    val hz = o.optJSONObject("stats")?.optDouble("hz", 0.0) ?: 0.0
                    consecutiveFails = 0
                    emit(
                        LinkEvent.Ok(
                            frame = frame,
                            rttMs = rtt,
                            hz = if (hz.isFinite()) hz else 0.0,
                            hasData = o.optBoolean("has_data", false),
                        )
                    )
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    // 单次抖动不该让界面闪成「连接失败」。
                    // 连续失败 3 次（约 300ms）才认定为真断了。
                    consecutiveFails++
                    if (consecutiveFails >= 3) {
                        emit(LinkEvent.Error(describe(e)))
                    }
                }
                delay(intervalMs)
            }
        } finally {
            unbind()
        }
    }.flowOn(Dispatchers.IO)

    // ---------------------------------------------------------- 网络绑定

    @Suppress("DEPRECATION")
    private fun bindToTargetNetwork() {
        val host = runCatching { Uri.parse(baseUrl).host }.getOrNull() ?: return
        if (!shouldPinToWifi(host)) return

        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE)
            as? ConnectivityManager ?: return

        val wifi = cm.allNetworks.firstOrNull { net ->
            cm.getNetworkCapabilities(net)?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        } ?: return

        pinnedToWifi = cm.bindProcessToNetwork(wifi)
        acquireWifiLock()
    }

    /**
     * 持有低延迟 WifiLock，阻止射频在两次轮询之间休眠。
     *
     * 实测：不持锁时 PC→手机 ICMP 是「最小 4ms / 平均 115ms / 最大 299ms」。
     * 最小值证明链路本身很快，平均值和最大值是 DTIM 缓存造成的 ——
     * 手机发完请求就进入省电，回程包被 AP 扣到下一个 DTIM 才投递，
     * 而 DTIM 通常是 100–300ms。对「实时仪表」来说这是致命的。
     */
    private fun acquireWifiLock() {
        if (wifiLock != null) return
        val wm = context.applicationContext
            .getSystemService(Context.WIFI_SERVICE) as? WifiManager ?: return

        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            WifiManager.WIFI_MODE_FULL_LOW_LATENCY
        } else {
            @Suppress("DEPRECATION")
            WifiManager.WIFI_MODE_FULL_HIGH_PERF
        }

        wifiLock = runCatching {
            wm.createWifiLock(mode, "dcs:bridge").apply {
                setReferenceCounted(false)
                acquire()
            }
        }.getOrNull()
    }

    private fun releaseWifiLock() {
        wifiLock?.let { lock ->
            runCatching { if (lock.isHeld) lock.release() }
        }
        wifiLock = null
    }

    private fun unbind() {
        releaseWifiLock()
        if (!pinnedToWifi) return
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE)
            as? ConnectivityManager
        cm?.bindProcessToNetwork(null)
        pinnedToWifi = false
    }

    /** 只有「局域网直连」才需要绑定；走公网/Tailscale 时交给系统决定。 */
    private fun shouldPinToWifi(host: String): Boolean {
        if (host.equals("localhost", ignoreCase = true)) return false
        val o = host.split(".").mapNotNull { it.toIntOrNull() }
        if (o.size != 4 || o.any { it !in 0..255 }) return false
        if (o[0] == 127) return false          // 回环（adb reverse）不要干预
        return o[0] == 10 ||
            (o[0] == 192 && o[1] == 168) ||
            (o[0] == 172 && o[1] in 16..31) ||
            (o[0] == 169 && o[1] == 254)
    }

    // ---------------------------------------------------------- 请求

    private fun fetch(path: String): String {
        // 成功路径**故意不调 disconnect()**：让 HttpURLConnection 复用 keep-alive 连接。
        // 10Hz 轮询下如果每次都新建一条 TCP，会把服务端的 accept 队列打爆
        // （Python socketserver 默认 backlog 只有 5），表现就是间歇性「连接被拒绝」，
        // 界面在已连接/失败之间乱跳。
        val conn = (URL(path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 2000
            readTimeout = 2000
            requestMethod = "GET"
            setRequestProperty("Accept", "application/json")
            useCaches = false
        }
        try {
            val code = conn.responseCode
            if (code != HttpURLConnection.HTTP_OK) {
                throw IllegalStateException("HTTP $code")
            }
            return conn.inputStream.bufferedReader().use { it.readText() }
        } catch (e: Exception) {
            // 出错才断开，避免坏连接留在池里
            conn.disconnect()
            throw e
        }
    }

    private fun describe(e: Exception): String = when (e) {
        is java.net.SocketTimeoutException -> "超时（服务器没响应）"
        is java.net.ConnectException -> "拒绝连接（地址或端口不对，或服务没开）"
        is java.net.UnknownHostException -> "地址解析失败"
        is java.net.NoRouteToHostException -> "网络不可达（不同网段或被隔离）"
        else -> e.message ?: e::class.java.simpleName
    }
}

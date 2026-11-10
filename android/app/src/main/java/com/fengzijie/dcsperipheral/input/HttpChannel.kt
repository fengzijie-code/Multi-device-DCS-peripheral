package com.fengzijie.dcsperipheral.input

import java.io.BufferedInputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URI

/**
 * 一条常连接的迷你 HTTP 客户端，专门用来 50Hz 发操纵量。
 *
 * 为什么不用 HttpURLConnection：
 *   倒不是为了性能。实测证明瓶颈不在客户端实现 —— 真正让每个请求多花
 *   20–45 ms 的是**服务端**把响应头和响应体分成两个小包写出去（详见
 *   tools/beacon.py 的 _send）。改成单包以后，用 HttpURLConnection 也能
 *   跑到 50 Hz。
 *
 *   仍然自己管连接，是因为这里需要三件 HttpURLConnection 给不了的事：
 *     - TCP_NODELAY。它不暴露底层 socket，只能听天由命。
 *     - 头部与体合成**一次** write。分两次小包是这类延迟的头号来源。
 *     - 恒定开销。没有对象池、没有重定向判定、没有 Cookie 处理，
 *       每帧的成本可预测 —— 飞行中的抖动比平均值更让人难受。
 *
 * 只实现真正用到的那一小块 HTTP：POST + Content-Length + keep-alive。
 * 不做 chunked、不做 100-continue、不跟重定向 —— 少一个分支就少一种
 * 在飞行中才暴露的失败方式。
 */
internal class HttpChannel(baseUrl: String) {

    private val host: String
    private val port: Int
    private val path: String

    private var sock: Socket? = null
    private var out: OutputStream? = null
    private var inp: InputStream? = null

    init {
        val u = URI(baseUrl.trim())
        host = u.host ?: "127.0.0.1"
        port = if (u.port > 0) u.port else 80
        val p = u.path.orEmpty()
        path = when {
            p.isBlank() -> "/input"
            p.endsWith("/") -> p + "input"
            else -> p + "/input"
        }
    }

    val endpoint: String get() = "http://$host:$port$path"

    private fun connect(): Boolean {
        close()
        return try {
            val s = Socket()
            // 这两行就是整个类存在的理由
            s.tcpNoDelay = true
            s.connect(InetSocketAddress(host, port), CONNECT_TIMEOUT_MS)
            s.soTimeout = READ_TIMEOUT_MS
            sock = s
            out = s.getOutputStream()
            inp = BufferedInputStream(s.getInputStream(), 256)
            true
        } catch (e: Exception) {
            close()
            false
        }
    }

    fun close() {
        runCatching { sock?.close() }
        sock = null
        out = null
        inp = null
    }

    /**
     * 返回：
     *    -1  链路失败（要重连）
     *     0  发出去了，但 PC 端 vjoy_out.py 没在跑
     *     1  发出去了，虚拟摇杆就绪
     *
     * 把 vJoy 存活塞进这个返回值，是为了不额外开一次查询。手机本来就
     * 每 20ms 读一次这个响应，顺路就能知道「飞机为什么不动」是出在
     * 桥接之前还是之后。
     */
    fun post(body: ByteArray): Int {
        if (sock == null && !connect()) return -1
        return try {
            val head = (
                "POST $path HTTP/1.1\r\n" +
                    "Host: $host:$port\r\n" +
                    "Content-Type: application/json\r\n" +
                    "Content-Length: ${body.size}\r\n" +
                    "\r\n"
                ).toByteArray(Charsets.US_ASCII)

            // 合成一次 write：拆成两次小包正是要避免的那件事
            val buf = ByteArray(head.size + body.size)
            System.arraycopy(head, 0, buf, 0, head.size)
            System.arraycopy(body, 0, buf, head.size, body.size)
            out!!.write(buf)
            out!!.flush()
            val code = readResponse()
            if (code !in 200..299) {
                close()
                return -1
            }
            if (lastBody.containsV1()) 1 else 0
        } catch (e: Exception) {
            close()
            -1
        }
    }

    /** 找响应体里的 `"v":1`。不引 JSON 库只为读一个布尔值。 */
    private fun ByteArray.containsV1(): Boolean {
        val pat = V1
        outer@ for (i in 0..size - pat.size) {
            for (j in pat.indices) if (this[i + j] != pat[j]) continue@outer
            return true
        }
        return false
    }

    private fun readResponse(): Int {
        val i = inp ?: throw IOException("连接已关闭")
        val statusLine = readLine(i) ?: throw IOException("对端已关闭")
        // 形如 "HTTP/1.1 200 OK"
        val code = statusLine.split(' ').getOrNull(1)?.toIntOrNull()
            ?: throw IOException("状态行无法解析：$statusLine")

        var len = 0
        while (true) {
            val line = readLine(i) ?: throw IOException("头部提前结束")
            if (line.isEmpty()) break
            val idx = line.indexOf(':')
            if (idx > 0 && line.substring(0, idx).equals("Content-Length", true)) {
                len = line.substring(idx + 1).trim().toIntOrNull() ?: 0
            }
        }
        // 必须把 body 读干净，否则下一帧会读到上一帧的残留，连接彻底错位
        val body = ByteArray(len.coerceIn(0, 4096))
        var off = 0
        while (off < body.size) {
            val n = i.read(body, off, body.size - off)
            if (n < 0) throw IOException("body 提前结束")
            off += n
        }
        lastBody = body
        return code
    }

    private var lastBody: ByteArray = ByteArray(0)

    /** 读一行（不含换行符）。逐字节读没问题：上层是 BufferedInputStream。 */
    private fun readLine(i: InputStream): String? {
        val sb = StringBuilder(64)
        while (true) {
            val c = i.read()
            if (c < 0) return if (sb.isEmpty()) null else sb.toString()
            if (c == '\n'.code) {
                if (sb.isNotEmpty() && sb[sb.length - 1] == '\r') sb.setLength(sb.length - 1)
                return sb.toString()
            }
            sb.append(c.toChar())
        }
    }

    private companion object {
        const val CONNECT_TIMEOUT_MS = 1200
        const val READ_TIMEOUT_MS = 1200
        val V1 = "\"v\":1".toByteArray(Charsets.US_ASCII)
    }
}

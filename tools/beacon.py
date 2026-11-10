#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beacon.py — 多端 DCS 外设 · P0 可达性信标

作用：用手机浏览器打开 PC 上的一个页面，直接回答「这两台设备之间到底通不通」。

这是 P0 最关键的验证工具。netprobe 只能排除死路，beacon 才能给出实测结论：
页面能加载 = 链路通；页面上的 RTT 和丢包率 = 这条链路的质量。

用法：
    python tools/beacon.py                  # 默认 8080 端口，同时监听 IPv4 与 IPv6
    python tools/beacon.py --port 9000
    python tools/beacon.py --ipv4-only

然后手机会看到类似这些地址，逐个试：
    http://10.180.211.30:8080/
    http://[2403:d400:1000:12:...]:8080/

注意：首次启动时 Windows 会弹防火墙授权框，**必须勾选「专用网络」并允许**，
否则手机永远连不上，而你会以为是校园网的问题。
"""

from __future__ import annotations

import argparse
import collections
import json
import socket
import socketserver
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    from netprobe import enumerate_ipv4, global_ipv6_addresses
except ImportError:  # 允许从别处直接跑
    def enumerate_ipv4():
        return []

    def global_ipv6_addresses():
        return []

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)

START_TIME = time.time()


# ---------------------------------------------------------------- 页面

def page_html(port: int) -> str:
    """极简但够用的自检页。深色主题，手机上一眼能读懂。返回 str（编码在发送时做）。"""
    return f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d1117">
<title>链路自检 · DCS 外设</title>
<style>
  :root {{
    --bg:#0d1117; --panel:#161b22; --line:#2a3038;
    --fg:#e6edf3; --dim:#8b949e; --teal:#3fb950; --amber:#d29922; --red:#f85149;
  }}
  * {{ box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
  html,body {{ margin:0; background:var(--bg); color:var(--fg);
    font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; }}
  .wrap {{ max-width:560px; margin:0 auto; padding:20px 16px 32px; }}
  .head {{ display:flex; align-items:center; gap:10px; margin:8px 0 18px; }}
  .dot {{ width:11px; height:11px; border-radius:50%; background:var(--amber);
    transition:background .3s; flex:none; }}
  .dot.ok {{ background:var(--teal); }} .dot.bad {{ background:var(--red); }}
  h1 {{ font-size:17px; font-weight:500; margin:0; }}
  .sub {{ color:var(--dim); font-size:12.5px; margin-left:auto; font-variant-numeric:tabular-nums; }}
  .hero {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:18px; margin-bottom:12px; }}
  .hero .label {{ color:var(--dim); font-size:12.5px; margin-bottom:6px; }}
  .rtt {{ font-size:44px; font-weight:500; font-variant-numeric:tabular-nums;
    line-height:1.05; letter-spacing:-1px; }}
  .rtt .unit {{ font-size:15px; color:var(--dim); margin-left:5px; letter-spacing:0; }}
  .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px;
    background:var(--line); border:1px solid var(--line); border-radius:14px;
    overflow:hidden; margin-bottom:12px; }}
  .stat {{ background:var(--panel); padding:12px 14px; }}
  .stat .k {{ color:var(--dim); font-size:11.5px; }}
  .stat .v {{ font-size:17px; font-variant-numeric:tabular-nums; margin-top:3px; }}
  canvas {{ width:100%; height:96px; display:block; margin-top:10px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:14px 16px; margin-bottom:12px; font-size:13px; color:var(--dim); }}
  .card b {{ color:var(--fg); font-weight:500; }}
  .kv {{ display:flex; justify-content:space-between; padding:5px 0;
    font-variant-numeric:tabular-nums; }}
  .kv span:last-child {{ color:var(--fg); }}
  .verdict {{ font-size:13.5px; padding:12px 14px; border-radius:12px;
    border:1px solid var(--line); background:var(--panel); color:var(--dim); }}
  .verdict b {{ color:var(--fg); }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px;
    background:#0b0f14; padding:1px 5px; border-radius:5px; color:#9ecbff; }}
</style></head><body>
<div class="wrap">
  <div class="head">
    <div class="dot" id="dot"></div>
    <h1>链路自检</h1>
    <div class="sub" id="clock">--:--:--</div>
  </div>

  <div class="hero">
    <div class="label">往返时延 RTT</div>
    <div class="rtt" id="rtt">--<span class="unit">ms</span></div>
    <canvas id="spark" width="600" height="96"></canvas>
  </div>

  <div class="stats">
    <div class="stat"><div class="k">最小</div><div class="v" id="pmin">--</div></div>
    <div class="stat"><div class="k">平均</div><div class="v" id="pavg">--</div></div>
    <div class="stat"><div class="k">最大</div><div class="v" id="pmax">--</div></div>
  </div>

  <div class="card">
    <div class="kv"><span>已发包</span><span id="sent">0</span></div>
    <div class="kv"><span>丢包</span><span id="lost">0</span></div>
    <div class="kv"><span>丢包率</span><span id="loss">0.0%</span></div>
    <div class="kv"><span>服务端地址</span><span>{'{server_ip}'}</span></div>
    <div class="kv"><span>服务端端口</span><span>{port}</span></div>
  </div>

  <div class="verdict" id="verdict">
    <b>正在测试…</b> 保持此页面在前台，至少观察 15 秒。
  </div>
</div>

<script>
(function () {{
  var hist = [], sent = 0, lost = 0, timer = null;
  var dot = document.getElementById('dot');
  var cv = document.getElementById('spark'), ctx = cv.getContext('2d');
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = cv.clientWidth * dpr; cv.height = 96 * dpr;

  function draw() {{
    var w = cv.width, h = cv.height;
    ctx.clearRect(0, 0, w, h);
    if (hist.length < 2) return;
    var max = Math.max.apply(null, hist), min = Math.min.apply(null, hist);
    var span = Math.max(max - min, 4);
    ctx.beginPath();
    for (var i = 0; i < hist.length; i++) {{
      var x = (i / (hist.length - 1)) * (w - 2) + 1;
      var y = h - ((hist[i] - min) / span) * (h - 12) - 6;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }}
    ctx.strokeStyle = '#3fb950'; ctx.lineWidth = 2 * dpr;
    ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke();
  }}

  function stats() {{
    if (!hist.length) return;
    var s = 0, mx = 0, mn = 1e9;
    for (var i = 0; i < hist.length; i++) {{
      s += hist[i]; if (hist[i] > mx) mx = hist[i]; if (hist[i] < mn) mn = hist[i];
    }}
    document.getElementById('pmin').textContent = Math.round(mn) + ' ms';
    document.getElementById('pavg').textContent = Math.round(s / hist.length) + ' ms';
    document.getElementById('pmax').textContent = Math.round(mx) + ' ms';
  }}

  var last = 0;
  function tick() {{
    var t0 = performance.now();
    sent++;
    fetch('/ping?t=' + Date.now(), {{ cache: 'no-store' }})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{
        var rtt = performance.now() - t0;
        hist.push(rtt);
        if (hist.length > 120) hist.shift();
        document.getElementById('rtt').innerHTML =
          Math.round(rtt) + '<span class="unit">ms</span>';
        document.getElementById('sent').textContent = sent;
        document.getElementById('lost').textContent = lost;
        document.getElementById('loss').textContent =
          (lost / sent * 100).toFixed(1) + '%';
        document.getElementById('clock').textContent =
          new Date(d.server_ms).toLocaleTimeString('zh-CN', {{ hour12: false }});
        dot.className = 'dot ok';
        stats(); draw();

        if (sent >= 30) {{
          var lr = lost / sent;
          var v = document.getElementById('verdict');
          if (lr === 0 && rtt < 30) {{
            v.innerHTML = '<b>链路优秀。</b>可以按路线图继续 —— 这个延迟做座舱操作完全够用。';
          }} else if (lr < 0.02 && rtt < 120) {{
            v.innerHTML = '<b>链路可用。</b>延迟偏高，仪表显示没问题，' +
              '密集操作会略有迟滞。建议记下这组数字，和 Tailscale 方案对比。';
          }} else {{
            v.innerHTML = '<b>链路勉强。</b>丢包或延迟已经会影响操作手感，' +
              '建议换 ③ Tailscale 或 ④ 中继再测一次对比。';
          }}
        }}
      }})
      .catch(function () {{
        lost++;
        document.getElementById('lost').textContent = lost;
        document.getElementById('loss').textContent =
          (lost / sent * 100).toFixed(1) + '%';
        dot.className = 'dot bad';
      }});
  }}

  tick();
  timer = setInterval(tick, 250);
}})();
</script>
</body></html>"""


# ---------------------------------------------------------------- 遥测汇聚

class TelemetryHub:
    """接收 mock / Export.lua 发来的 UDP 帧，保存最新一帧与统计。

    P0 阶段的桥接服务简化版：不做归一化、不做鉴权、不做多客户端状态，
    只做「收 → 存 → 吐」。P1 换 Rust 之后这个类会被替换掉，
    但它定义的 /state JSON 结构会被沿用。
    """

    def __init__(self, window: int = 120):
        self._lock = threading.Lock()
        self._latest: dict | None = None
        self._seq = 0
        self._rx = 0
        self._bad = 0
        self._last_rx = 0.0
        self._times: collections.deque = collections.deque(maxlen=window)

    def feed(self, data: bytes) -> None:
        try:
            obj = json.loads(data.decode("utf-8"))
            if not isinstance(obj, dict):
                raise ValueError("not an object")
        except Exception:
            with self._lock:
                self._bad += 1
            return

        now = time.time()
        with self._lock:
            self._latest = obj
            self._seq += 1
            self._rx += 1
            self._last_rx = now
            self._times.append(now)

    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            hz = 0.0
            if len(self._times) >= 2:
                span = self._times[-1] - self._times[0]
                if span > 0:
                    hz = (len(self._times) - 1) / span
            age_ms = int((now - self._last_rx) * 1000) if self._last_rx else None
            # 超过 2 秒没收到，认为上游已停，别让客户端看着旧数据以为还活着
            fresh = age_ms is not None and age_ms < 2000
            return {
                "server_ms": int(now * 1000),
                "seq": self._seq,
                "has_data": self._latest is not None and fresh,
                "frame": self._latest if fresh else None,
                "stats": {
                    "rx": self._rx,
                    "bad": self._bad,
                    "hz": round(hz, 1),
                    "age_ms": age_ms,
                },
            }


HUB = TelemetryHub()


def udp_listener(port: int, hub: TelemetryHub, stop: threading.Event) -> None:
    """只绑回环：mock 与 Export.lua 都发到本机，不该暴露到局域网。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
    except OSError as e:
        print(f"  [x] UDP {port} 绑定失败：{e}（可能已被 mock_export 占用）")
        s.close()
        return

    s.settimeout(1.0)
    print(f"  UDP 监听 127.0.0.1:{port} —— 等待 mock 或 DCS 发数据")
    try:
        while not stop.is_set():
            try:
                data, _ = s.recvfrom(16384)
            except socket.timeout:
                continue
            except OSError:
                break
            hub.feed(data)
    finally:
        s.close()


# ---------------------------------------------------------------- 服务

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # 开 keep-alive，这样 RTT 才反映真实链路而不是每次都重建 TCP
    server_version = "DCSBeacon/0.1"

    # 关键：关掉 Nagle。
    #
    # 我们把响应分两次写（状态行+头部一次，body 一次），都是小包。
    # Nagle 会把第二个小包扣住，等第一个包的 ACK；而 Android 的延迟 ACK
    # 会等 100–200ms 才回。两者凑在一起，实测有线上 RTT 从 2ms 涨到 900ms。
    # 走 USB（adb reverse）时因为 adbd 在中间转发，这个效应被掩盖了，
    # 换成真实 Wi-Fi 才暴露出来 —— 典型的「挪到真链路才炸」的问题。
    disable_nagle_algorithm = True

    def log_message(self, fmt, *args):
        # /ping 每 250ms 一次，全打出来会把控制台刷爆；只记录页面级请求
        try:
            msg = fmt % args
        except Exception:
            msg = str(fmt)
        if "/ping" in msg:
            return
        sys.stderr.write(f"  [{self.client_address[0]}] {msg}\n")

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        u = urlparse(self.path)
        local_ip = self.connection.getsockname()[0]

        if u.path == "/ping":
            body = json.dumps({
                "now": time.time(),
                "server_ms": int(time.time() * 1000),
                "uptime_s": round(time.time() - START_TIME, 1),
                "peer": self.client_address[0],
            }).encode()
            self._send(200, body, "application/json")
            return

        if u.path == "/state":
            body = json.dumps(HUB.snapshot(), ensure_ascii=False).encode()
            self._send(200, body, "application/json")
            return

        if u.path == "/info":
            body = json.dumps({
                "ipv4": enumerate_ipv4(),
                "ipv6": global_ipv6_addresses(),
                "uptime_s": round(time.time() - START_TIME, 1),
            }, ensure_ascii=False, indent=2).encode()
            self._send(200, body, "application/json")
            return

        if u.path in ("/", "/index.html"):
            html = page_html(self.server.server_address[1]).replace(
                "{server_ip}", str(local_ip)
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


class V4Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # 默认 backlog 只有 5。客户端 10Hz 轮询时，一旦不复用长连接，
    # 新建连接的速度就会超过 accept 的速度，表现为「连接被拒绝」。
    request_queue_size = 64


class V6Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    address_family = socket.AF_INET6
    request_queue_size = 64


# ---------------------------------------------------------------- 启动

def start_servers(port: int, ipv4_only: bool) -> list:
    servers = []

    try:
        s4 = V4Server(("0.0.0.0", port), Handler)
        threading.Thread(target=s4.serve_forever, daemon=True).start()
        servers.append(("IPv4 0.0.0.0", s4))
    except OSError as e:
        print(f"  [x] IPv4 :{port} 起不来 —— {e}")

    if not ipv4_only:
        try:
            s6 = V6Server(("::", port), Handler)
            threading.Thread(target=s6.serve_forever, daemon=True).start()
            servers.append(("IPv6 ::", s6))
        except OSError as e:
            print(f"  [–] IPv6 :{port} 不可用（{e}），仅 IPv4 运行")

    return servers


def main() -> int:
    ap = argparse.ArgumentParser(description="多端 DCS 外设 · 可达性信标")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--ipv4-only", action="store_true", help="不监听 IPv6")
    ap.add_argument("--udp-in", type=int, default=5010,
                    help="遥测 UDP 端口，0 表示不接收遥测")
    args = ap.parse_args()

    stop = threading.Event()

    print()
    print("═" * 62)
    print("  可达性信标 · 用手机浏览器打开下面任意一个地址")
    print("═" * 62)

    servers = start_servers(args.port, args.ipv4_only)
    if not servers:
        print("  [x] 没有成功监听任何地址，检查端口是否被占用")
        return 1

    if args.udp_in:
        threading.Thread(
            target=udp_listener,
            args=(args.udp_in, HUB, stop),
            daemon=True,
        ).start()

    print()
    print("· 候选地址")
    n = 0
    for a in enumerate_ipv4():
        if a.get("virtual"):
            continue
        print(f"  http://{a['ip']}:{args.port}/          {a['adapter']}")
        n += 1
    for ip in global_ipv6_addresses():
        print(f"  http://[{ip}]:{args.port}/")
        n += 1
    if n == 0:
        print("  （没找到可用地址，检查 Wi-Fi 连接）")

    print()
    print("· 提示")
    print("  1) 手机必须连同一个 Wi-Fi（或已接入同一 Tailscale 网络）")
    print("  2) 首次启动 Windows 会弹防火墙框，务必勾选「专用网络」并允许")
    print("  3) 页面上能看到 RTT 数字跳动 = 链路通；一直 --  = 不通")
    print("  4) 逐个地址试，哪个通用哪个 —— 不同地址走的是不同路径")
    if args.udp_in:
        print(f"  5) 遥测出口 http://<上面的IP>:{args.port}/state —— Android 客户端读这个")
    print()
    print(f"  服务端时间 {datetime.now().strftime('%H:%M:%S')}   Ctrl+C 退出")
    print("═" * 62)
    print()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        stop.set()
        for _, s in servers:
            try:
                s.shutdown()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

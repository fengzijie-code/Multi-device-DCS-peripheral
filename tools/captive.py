#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
captive.py — 有线直连助手 · 喂饱 iOS 的联网探测

背景（为什么必须有这个）：

    iPad 用网线直连电脑（无 DHCP、无路由器）时，两边各自自分配地址，
    ping 全通，但 **Safari 会拒绝往这条网卡上发任何请求** —— iOS 把
    「探测不到互联网」的网卡标记为离线，浏览器（以及很多 app）直接不碰它。
    现象就是：ping 通、curl 通，iPad 上却显示「无网络 / Safari 无法打开网页」。

原理：

    iOS 判断「这个网络有没有网」靠一个固定的探测请求：
        DNS 解析 captive.apple.com →
        GET http://captive.apple.com/hotspot-detect.html → 期待正文 "Success"
    只要这两个请求被电脑应答成功，iOS 就把网络标记为「有互联网」，
    Safari 立刻恢复正常 —— 哪怕「互联网」其实是我们自己伪装的。

所以这个进程干两件事：

    1. DNS（UDP 53）：所有 A 查询一律回答本机 IP（询问者和哪个网卡同段
       就答哪个网卡的 IP，拿不准就退回第一个非虚拟 IP）。
    2. HTTP（TCP 80）：iOS / Windows / Android 的探测路径全部答对 ——
       captive.apple.com → "Success"，generate_204 → 204，msftconnecttest → 其正文。

配套设置（iPad 侧）：

    设置 → 以太网 → 配置 DNS → 手动 → 填电脑的 IP（如 192.168.77.1）
    没有这一步 iOS 连 captive.apple.com 都解析不到，探测无从谈起。

Windows 防火墙：53/UDP 与 80/TCP 需要放行 —— 用 tools\\open-firewall.bat
（右键管理员运行），它已经把这两条加进去了。

纯标准库，无依赖。端口被占就跳过对应服务，不挡别的启动。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import netprobe  # 同目录，纯标准库
except Exception:            # pragma: no cover
    netprobe = None

FORCED_IP = ""               # --ip 指定后就不再按询问者网段自动挑


# ---------------------------------------------------------------- 本机 IP

def local_ips() -> list[dict]:
    try:
        return [e for e in netprobe.enumerate_ipv4() if not e.get("virtual")]
    except Exception:
        return []


def local_ip_for(peer_ip: str) -> str | None:
    """挑一个和询问者同网段的本机 IP；挑不出就退回第一个非虚拟 IP。

    直连场景 iPad 从 169.254.x.x 或 192.168.77.x 问过来，必须答那个段的
    地址 —— 答成 Wi-Fi 的 10.x.x.x，iPad 照样连不上，探测等于没喂。
    """
    if FORCED_IP:
        return FORCED_IP
    ips = local_ips()
    if not ips:
        return None
    try:
        import ipaddress
        peer = ipaddress.ip_address(peer_ip)
        for e in ips:
            if not e.get("mask"):
                continue
            try:
                net = ipaddress.ip_network(f"{e['ip']}/{e['mask']}", strict=False)
                if peer in net:
                    return e["ip"]
            except ValueError:
                continue
    except Exception:
        pass
    return ips[0]["ip"]


# ---------------------------------------------------------------- DNS（UDP 53）

def _read_name(data: bytes, off: int) -> tuple[str, int]:
    """解析域名（只用于跳过问题段；遇到压缩指针就停在那）。"""
    labels: list[str] = []
    while off < len(data):
        l = data[off]
        if l == 0:
            off += 1
            break
        if l & 0xC0 == 0xC0:                      # 压缩指针
            off += 2
            break
        labels.append(data[off + 1: off + 1 + l].decode("latin-1", "replace"))
        off += 1 + l
    return ".".join(labels), off


def build_response(query: bytes, answer_ip: str) -> bytes | None:
    """最小 DNS 应答：问题段原样回，A 查询补一条 A 记录，其余给空答。"""
    if len(query) < 12:
        return None
    tid = query[0:2]
    try:
        qdcount = int.from_bytes(query[4:6], "big")
    except Exception:
        return None
    if qdcount < 1:
        return None

    off = 12
    name, off = _read_name(query, off)
    if off + 4 > len(query):
        return None
    qtype = int.from_bytes(query[off:off + 2], "big")
    question = query[12:off + 4]                  # 原样回显（含类型/类）

    flags = 0x8180                                # QR=1, RD=1, RA=1
    header = tid + flags.to_bytes(2, "big") + (1).to_bytes(2, "big")

    if qtype == 1:                                # A
        parts = [int(x) for x in answer_ip.split(".")]
        if len(parts) != 4:
            return None
        rdata = bytes(parts)
        answer = (b"\xc0\x0c"                    # 名字压缩指针 → 问题段
                  + (1).to_bytes(2, "big")       # TYPE A
                  + (1).to_bytes(2, "big")       # CLASS IN
                  + (60).to_bytes(4, "big")      # TTL
                  + (4).to_bytes(2, "big") + rdata)
        return header + (1).to_bytes(2, "big") + question + answer

    # AAAA / TXT / 其余：空答（NOERROR, 0 条记录）——iOS 会自己退回 A
    return header + (0).to_bytes(2, "big") + question


class DnsServer(threading.Thread):
    def __init__(self, port: int = 53):
        super().__init__(daemon=True, name="dns")
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # bind 放在构造里：起不来当场抛 OSError，main 才能接住并优雅跳过
        self.sock.bind(("0.0.0.0", self.port))

    def run(self) -> None:
        print("  [captive] DNS    :53 就绪 —— 所有域名都答成本机地址", flush=True)
        while True:
            try:
                data, addr = self.sock.recvfrom(1500)
            except OSError:
                return
            answer_ip = local_ip_for(addr[0]) or "127.0.0.1"
            resp = build_response(data, answer_ip)
            if resp:
                try:
                    self.sock.sendto(resp, addr)
                except OSError:
                    pass


# ---------------------------------------------------------------- HTTP（TCP 80）

class ProbeHandler(BaseHTTPRequestHandler):
    """iOS / Windows / Chrome 的联网探测各要各的正文，全部对上。"""

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        host = (self.headers.get("Host") or "").lower()

        if "generate_204" in path or "connectivitycheck" in host:
            code, body = 204, b""                          # Android / Chrome
        elif "msftconnecttest" in host or path == "/connecttest.txt":
            code, body = 200, b"Microsoft Connect Test"    # Windows NCSI
        elif "msftncsi" in host:
            code, body = 200, b"Microsoft NCSI"
        else:
            # captive.apple.com/hotspot-detect.html 及一切没认出的探测：
            # iOS 认准正文就是 "Success"
            code, body = 200, b"Success"

        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # 探测每分钟好几次，全打出来刷屏；只打第一条让用户知道它活了
        if not getattr(self.server, "_logged_probe", False):
            self.server._logged_probe = True
            print(f"  [captive] HTTP   :80 收到第一条探测（{self.headers.get('Host')}）"
                  f"—— iOS 这下该认这个网了", flush=True)


class HttpServer(threading.Thread):
    def __init__(self, port: int = 80):
        super().__init__(daemon=True, name="http")
        self.port = port
        self.httpd = ThreadingHTTPServer(("0.0.0.0", port), ProbeHandler)
        self.httpd._logged_probe = False

    def run(self) -> None:
        print(f"  [captive] HTTP   :{self.port} 就绪 —— 探测一律答 Success", flush=True)
        self.httpd.serve_forever()


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="iOS 联网探测应答器（有线直连用）")
    ap.add_argument("--dns-port", type=int, default=53)
    ap.add_argument("--http-port", type=int, default=80)
    ap.add_argument("--ip", default="",
                    help="DNS 应答用的本机 IP（默认按询问者网段自动挑）")
    args = ap.parse_args()

    print("  [captive] 有线直连助手 —— 喂 iOS 的联网探测，让 Safari 肯用这条网线", flush=True)
    if args.ip:
        global FORCED_IP
        FORCED_IP = args.ip

    started = 0
    try:
        dns = DnsServer(args.dns_port)
        dns.start()
        started += 1
    except OSError as e:
        print(f"  [captive] DNS :{args.dns_port} 起不来（{e}）—— 已跳过。", flush=True)

    try:
        http = HttpServer(args.http_port)
        http.start()
        started += 1
    except OSError as e:
        print(f"  [captive] HTTP :{args.http_port} 起不来（{e}）—— 已跳过。", flush=True)

    if started == 0:
        print("  [captive] 两个端口都起不来，本进程退出（不影响其它服务）。", flush=True)
        return 0

    print(f"  [captive] iPad 设置 → 以太网 → 配置 DNS → 手动 → 填本机 IP。", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

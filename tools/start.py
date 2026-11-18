#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start.py — 双击一次就能飞

为什么要有这一层，而不是让 .bat 直接调 run-all.py：

  1. 中文。批处理里的中文会被控制台代码页搅成乱码，然后后面每一行都被
     当成命令解析（这是 .bat 里最经典的连环炸）。所以 .bat 保持纯 ASCII、
     只干一件事：找 python、把参数原样递过来。所有文字都在这儿，UTF-8。
  2. 预检要能看见真实的失败原因。证书过期、证书里没有当前这个 IP、
     端口被上一次的窗口占着、防火墙没放行 —— 这四件事在 iPad 上的表现
     **一模一样**，都是「打不开 / 已丢失网络连接」。与其让人对着 iPad 猜，
     不如在启动时逐条查一遍。
  3. 上手地址要具体到 IP。以前只说「打开 http://<本机IP>:8080/yoke」，
     而热点网卡是 192.168.137.1、有线是 10.180.211.30 —— 用户得自己去
     ipconfig 里翻。这里等服务起来后直接问 /info，把真实地址印出来。

用法：
    python tools\\start.py              iPad（默认）
    python tools\\start.py mock         同上，再起 60Hz 假遥测（真 DCS 在跑时别开）
    python tools\\start.py --phone       手机 USB 模式（含 adb 检查与隧道）
    python tools\\start.py --firewall    顺手加一次防火墙规则（会弹 UAC）

停止：Ctrl+C，然后按 Y 结束批处理任务。vJoy 会先回中。
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import importlib.util
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CERTS = HERE / "certs"
RUN_ALL = HERE / "run-all.py"

# 规则名必须和 tools/open-firewall.bat 里的一致，否则会重复加第二条
FW_RULE = "DCS Peripheral Bridge"


def _out_ok(ch: str) -> bool:
    """控制台编码放不下这个字符就退化成 ASCII，别打出一堆问号。"""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        ch.encode(enc)
        return True
    except Exception:
        return False


OK = "✓" if _out_ok("✓") else "+"
NO = "✗" if _out_ok("✗") else "x"
WARN = "!" if not _out_ok("⚠") else "⚠"


class C:
    """和控制台颜色。run-all.py 用的是同一组转义，保持观感一致。"""

    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    C = "\033[36m"
    D = "\033[2m"
    B = "\033[1m"
    X = "\033[0m"


def enable_ansi() -> None:
    """老版 conhost 默认不解析 ANSI，打开 VT 处理；失败就静默降级。"""
    if os.name != "nt":
        return
    try:
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


def head(text: str) -> None:
    print()
    print("═" * 66)
    print(f"  {C.B}{text}{C.X}")
    print("═" * 66)


def line(tag: str, ok: bool | None, msg: str, extra: str = "") -> None:
    """tag 是固定宽度的一列，便于上下对齐着扫。"""
    if ok is True:
        mark, col = OK, C.G
    elif ok is False:
        mark, col = NO, C.R
    else:
        mark, col = WARN, C.Y
    print(f"  [{tag}] {col}{mark}{C.X} {msg}")
    if extra:
        for ln in extra.splitlines():
            print(f"          {C.D}{ln}{C.X}")


# ------------------------------------------------------------------ 证书

def current_ips() -> list[str]:
    try:
        sys.path.insert(0, str(HERE))
        import netprobe  # noqa: WPS433

        return [e["ip"] for e in netprobe.enumerate_ipv4() if not e.get("virtual")]
    except Exception:
        return []


def read_cert() -> tuple[dt.datetime | None, list[str]]:
    """返回 (到期时间, SAN 里的 IP 列表)。读不出来就返回 (None, [])。"""
    crt = CERTS / "server.crt"
    if not crt.is_file():
        return None, []
    try:
        d = ssl._ssl._test_decode_cert(str(crt))   # noqa: SLF001  标准库没有公开接口
    except Exception:
        return None, []
    try:
        na = dt.datetime.strptime(d["notAfter"], "%b %d %H:%M:%S %Y %Z")
        na = na.replace(tzinfo=dt.timezone.utc)
    except Exception:
        na = None
    ips = [v for k, v in d.get("subjectAltName", ()) if k == "IP Address"]
    return na, ips


def ensure_cert(force_regen: bool = False) -> bool:
    """证书是 iPad 那条路上最贵的一次踩坑，所以每次启动都查三件事：

    1. 文件在不在
    2. 有没有过期 / 快到 398 天的 iOS 上限（超了 Safari 直接说"网络丢失"）
    3. **SAN 里有没有当前这个 IP** —— 换了热点、换了网线，IP 就变了，
       证书里没有它 Safari 会弹"不是私密连接"。根 CA 不受影响，
       所以重签 leaf 之后 iPad **不需要重装描述文件**。
    """
    na, sans = read_cert()
    ips = current_ips()

    if na is None:
        need, why = True, "没有证书（首次运行）"
    elif (na - dt.datetime.now(dt.timezone.utc)).days < 14:
        need, why = True, "证书 14 天内到期"
    else:
        missing = [ip for ip in ips if ip not in sans]
        need, why = bool(missing), "证书里没有当前 IP：" + "、".join(missing) if missing else ""

    if not need and not force_regen:
        days = (na - dt.datetime.now(dt.timezone.utc)).days
        line("证书", True, f"有效，还剩 {days} 天，已含 {len(ips)} 个本机 IP")
        return True

    print(f"  [证书] {C.Y}…{C.X} {why}，正在重签")
    argv = [sys.executable, str(HERE / "make-cert.py")]
    for ip in ips:
        argv += ["--ip", ip]
    p = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = (p.stdout or "") + (p.stderr or "")
        line("证书", False, "重签失败 —— 多半是 PATH 里没有 openssl",
             "\n".join(tail.strip().splitlines()[-6:]))
        return False
    line("证书", True, "已重签（根证书没变，iPad 不用重装描述文件）")
    return True


# ------------------------------------------------------------------ 端口

def _proc_name(pid: str) -> str:
    try:
        q = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True,
                           encoding="gbk", errors="replace")
        return (q.stdout or "").split(",")[0].strip('"')
    except Exception:
        return "?"


def port_holders(port: int, udp: bool = False) -> list[str]:
    """谁占着这个端口，返回 ["python.exe (PID 1234)", …]。

    为什么不靠 bind 试探：Windows 的 SO_REUSEADDR 语义和 Unix 不一样 ——
    端口正被别人 listen 着，加了 SO_REUSEADDR 的 bind **照样成功**
    （这是 Windows 上端口劫持能成立的根因）。所以试探 bind 得到的是
    假的「空闲」，而 run-all 起来之后 beacon 才在 listen 那一步失败，
    表现成「窗口一闪」「页面打不开」。netstat 的 LISTENING 行才是
    「有人在这里接客」的权威判据。
    """
    try:
        p = subprocess.run(["netstat", "-ano"], capture_output=True,
                           text=True, encoding="gbk", errors="replace")
    except Exception:
        return []
    out, seen = [], set()
    for row in (p.stdout or "").splitlines():
        parts = row.split()
        if len(parts) < 4:
            continue
        proto, local, pid = parts[0], parts[1], parts[-1]
        if proto.upper() != ("UDP" if udp else "TCP"):
            continue
        if not local.endswith(f":{port}") or not pid.isdigit() or pid in seen:
            continue
        if not udp and parts[-2].upper() != "LISTENING":
            continue
        seen.add(pid)
        out.append(f"{_proc_name(pid)} (PID {pid})")
    return out


def check_ports(port: int, tls_port: int, vjoy_port: int, no_vjoy: bool) -> bool:
    bad = []
    for p, what, udp in ((port, "桥接 HTTP", False),
                         (tls_port, "HTTPS", False),
                         (vjoy_port, "虚拟摇杆 UDP", True)):
        if p == vjoy_port and no_vjoy:
            continue
        who = port_holders(p, udp)
        if not who and udp:
            # UDP 没有 LISTENING 状态，只能试绑；UDP 不走 SO_REUSEADDR，绑失败就是真占用
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                who = ["某个进程"]
            finally:
                s.close()
        if who:
            bad.append(f"{p}（{what}）← " + "、".join(who))
    if bad:
        pids = re.findall(r"PID (\d+)", " ".join(bad))
        hint = "上一次那个窗口多半还没关。关掉它，或者直接重启一次电脑。"
        if pids:
            hint += "\n只想强杀的话：taskkill /F /PID " + " /PID ".join(pids)
        line("端口", False, "被占用：" + "；".join(bad), hint)
        return False
    line("端口", True, f"{port} / {tls_port} / {vjoy_port} 都空闲")
    return True


# ------------------------------------------------------------------ 防火墙

def firewall_ok() -> bool | None:
    if os.name != "nt":
        return None
    try:
        p = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule",
                            f"name={FW_RULE}"],
                           capture_output=True, text=True,
                           encoding="gbk", errors="replace")
        return p.returncode == 0
    except Exception:
        return None


def elevate_firewall() -> None:
    """用 ShellExecuteW 的 runas 拉起那个 .bat，会弹一次 UAC。"""
    bat = HERE / "open-firewall.bat"
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", f'/c "{bat}"', None, 1)
    except Exception as e:
        print(f"  {C.R}{NO}{C.X} 提权失败：{e}")


# ------------------------------------------------------------------ 上手卡片

def http_get(url: str, timeout: float = 3.0) -> tuple[int, str]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def show_card(port: int) -> None:
    """等服务真起来之后再去问 /info —— 这样印出来的 IP 就是服务在听的那些，
    不是 ipconfig 里可能存在的网关、虚拟网卡、169.254 自分配地址。"""
    base = f"http://127.0.0.1:{port}"
    info = None
    for _ in range(40):                     # 最多等 8 秒
        time.sleep(0.2)
        code, _err = http_get(base + "/info")
        if code == 200:
            try:
                with urllib.request.urlopen(base + "/info", timeout=2) as r:
                    info = json.load(r)
                break
            except Exception:
                pass
    if not info:
        print(f"\n  {C.Y}{WARN}{C.X} 8 秒内没等到服务应答，"
              f"看上面有没有 [beacon] 的报错。\n")
        return

    ips = [e["ip"] for e in info.get("ipv4", []) if not e.get("virtual")]
    tls = int(info.get("https_port") or 0)

    code_h, _ = http_get(f"{base}/yoke")
    code_s, err_s = (http_get(f"https://127.0.0.1:{tls}/yoke") if tls else (0, "没开"))

    print()
    print("  " + "─" * 62)
    if tls:
        print(f"  {C.B}iPad 打开这一条（地址栏必须带 https://）{C.X}")
        for ip in ips:
            print(f"    {C.C}https://{ip}:{tls}/yoke{C.X}")
        print()
        print(f"  {C.D}http 版只用来装一次根证书 —— 体感在 http 下拿不到传感器{C.X}")
        print(f"  {C.D}http://{ips[0] if ips else '<本机IP>'}:{port}/yoke{C.X}")
        print()
        print(f"  {C.D}第一次用：打开 http 版 → 点「体感」→ 按页面上的三步装证书{C.X}")
        print(f"  {C.D}装完加一次「添加到主屏幕」，以后点图标就是全屏{C.X}")
    else:
        print(f"  {C.B}iPad 打开这一条{C.X}")
        for ip in ips:
            print(f"    {C.C}http://{ip}:{port}/yoke{C.X}")
        print()
        print(f"  {C.Y}{WARN}{C.X} 这次没开 HTTPS（证书没生成成功），")
        print(f"    {C.D}结果是页面能开、但「体感」拿不到陀螺仪。{C.X}")
    print("  " + "─" * 62)

    marks = []
    marks.append(f"http {C.G}{code_h}{C.X}" if code_h == 200
                 else f"http {C.R}{code_h or '无应答'}{C.X}")
    if tls:
        marks.append(f"https {C.G}{code_s}{C.X}" if code_s == 200
                     else f"https {C.R}{code_s or '无应答'}{C.X}")
    print("  自检：" + "  ·  ".join(marks))
    if tls and code_s != 200:
        print(f"  {C.Y}{WARN}{C.X} https 没起来。看 {C.B}tools\\.tls.log{C.X}：")
        print(f"    {C.D}OK = 握手成功；FAIL SSLError = 证书问题；{C.X}")
        print(f"    {C.D}日志里压根没有这个 IP = 网络/防火墙问题（不是证书）{C.X}")
    if code_h != 200 and not tls:
        print(f"  {C.R}{NO}{C.X} 页面都打不开，先看上面的 [beacon] 日志。")
    print()


# ------------------------------------------------------------------ 主流程

def load_runall():
    spec = importlib.util.spec_from_file_location("dcs_runall", str(RUN_ALL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)        # run-all.py 有 __main__ 守卫，这儿不会真的跑
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description="DCS 外设一键启动")
    ap.add_argument("mode", nargs="?", default="", choices=["", "ipad", "mock", "phone"],
                    help="ipad（默认）/ mock / phone")
    ap.add_argument("--phone", action="store_true", help="手机 USB 模式")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--tls-port", type=int, default=8443)
    ap.add_argument("--vjoy-port", type=int, default=5011)
    ap.add_argument("--no-vjoy", action="store_true", help="不启动 vJoy 输出")
    ap.add_argument("--firewall", action="store_true",
                    help="加一次防火墙放行规则（会弹 UAC）")
    ap.add_argument("--no-check", action="store_true", help="跳过预检（排障时用）")
    args = ap.parse_args()

    enable_ansi()
    os.chdir(ROOT)          # run-all 里用的是相对路径

    phone = args.phone or args.mode == "phone"
    mock = args.mode == "mock"

    head("DCS 外设 · 一键启动" + ("（手机 USB）" if phone else "（iPad）"))

    if not args.no_check:
        cert_ok = ensure_cert()
        if not check_ports(args.port, args.tls_port, args.vjoy_port, args.no_vjoy):
            print()
            return 2
        fw = firewall_ok()
        if fw is False:
            line("防火墙", None, "没有放行规则 —— iPad 连不上，八成就卡在这",
                 f"以管理员身份运行一次 tools\\open-firewall.bat\n"
                 f"或者：python tools\\start.py --firewall")
            if args.firewall:
                print(f"  [防火墙] 正在提权添加规则 …")
                elevate_firewall()
        elif fw is True:
            line("防火墙", True, f"已有放行规则「{FW_RULE}」")
        if not cert_ok:
            print(f"\n  {C.Y}{WARN}{C.X} 没有 HTTPS 证书，继续启动，"
                  f"但体感用不了。\n")

    # 服务起来之后再把上手地址印出来。用后台线程，是因为 run-all.main()
    # 会一直阻塞在自己的等待循环里，没有"启动完成"的回调可以挂。
    threading.Thread(target=show_card, args=(args.port,), daemon=True).start()

    argv = ["--port", str(args.port), "--tls-port", str(args.tls_port),
            "--vjoy-port", str(args.vjoy_port)]
    if not phone:
        argv += ["--no-usb", "--no-watch"]
    if args.no_vjoy:
        argv += ["--no-vjoy"]
    if mock:
        argv += ["--mock"]

    mod = load_runall()
    old = sys.argv
    sys.argv = ["run-all.py"] + argv
    try:
        return int(mod.main() or 0)
    finally:
        sys.argv = old


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

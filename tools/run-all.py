#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run-all.py — 一键启动全部服务（单窗口）

拉起三个进程并把它们的输出打上标签汇总到同一个窗口：

    [beacon]  HTTP :8080 + 遥测 UDP :5010
    [watch ]  adb reverse 看守（USB 断开/重启后自动重建隧道）
    [vjoy  ]  手机操纵量 → vJoy 驱动
    [mock  ]  60Hz 假遥测（--mock 才启动，有真 DCS 时不要开）

为什么做成一个窗口而不是开四个 cmd：
    四个窗口的问题是「出事了不知道该看哪个」，而且关的时候容易漏一个、
    下次启动就撞端口。这里把输出统一加前缀，一眼能分清是谁在说话；
    某个子进程意外退出会自动重拉，整个窗口 Ctrl+C 一起收工。

为什么子进程仍然共享这个控制台（不另开窗口）：
    Ctrl+C 是**控制台级**事件，会发给所有挂在同一个控制台上的进程。
    vjoy_out 收到 SIGINT 才会走 ResetVJD 把杆回中 —— 如果用
    TerminateProcess 杀掉它，atexit 和信号处理器都不会跑，vJoy 里的
    杆位就留在最后那一帧上了。
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 标签、颜色、命令行（%s 会填进端口等参数）
TAG_COLOR = {
    "beacon": "\033[36m",   # 青
    "watch": "\033[35m",    # 洋红
    "vjoy": "\033[32m",     # 绿
    "mock": "\033[33m",     # 黄
}

MAX_RESTART = 3          # 60 秒窗口内最多重拉几次
RESTART_WINDOW = 60.0


# ------------------------------------------------------------------ 预检

def find_adb() -> str | None:
    """先找 PATH，再找 Android Studio 的默认装法。

    为什么不把这段留在 .bat 里：批处理没法在这里实测（沙箱禁止从 shell
    调 cmd），一旦引号或 goto 写错，只有用户双击的时候才会暴露。放进
    Python 就能单独跑、单独验。
    """
    p = shutil.which("adb")
    if p:
        return p
    cand = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Android", "Sdk", "platform-tools", "adb.exe",
    )
    return cand if os.path.isfile(cand) else None


def adb_run(adb: str, *args: str, timeout: float = 10) -> tuple[int, str]:
    """返回 (退出码, 合并后的输出)。"""
    try:
        p = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"
    raw = (p.stdout or b"") + (p.stderr or b"")
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return p.returncode, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return p.returncode, ""


def list_devices(adb: str) -> list[tuple[str, str]]:
    """返回 [(序列号, 状态)]。状态是 device / unauthorized / offline。"""
    _, out = adb_run(adb, "devices")
    res = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ("device", "unauthorized", "offline"):
            res.append((parts[0], parts[1]))
    return res


def wait_device(adb: str, seconds: float = 20.0) -> tuple[str | None, str]:
    """等一台授权好的设备。返回 (序列号, 状态)；没等到就是 (None, 原因)。"""
    adb_run(adb, "start-server")
    deadline = time.monotonic() + seconds
    last = "none"
    while time.monotonic() < deadline:
        for serial, state in list_devices(adb):
            if state == "device":
                return serial, "device"
            last = state
        time.sleep(1.0)
    return None, last


def setup_tunnel(adb: str, port: int) -> bool:
    """建 adb reverse。

    不只看 `reverse --list`：那要多一次往返，而 adb 服务刚起来/刚重启时
    这一次往返很容易拿到空结果（服务正在重启）。`reverse` 命令成功时会
    把映射到的端口打到 stdout 上，用它判定更直接。两个都试。
    """
    adb_run(adb, "reverse", "--remove-all")
    for attempt in range(2):
        rc, out = adb_run(adb, "reverse", f"tcp:{port}", f"tcp:{port}")
        if rc == 0 and str(port) in out:
            return True
        if f"tcp:{port}" in adb_run(adb, "reverse", "--list")[1]:
            return True
        time.sleep(0.6)
    return False


# ------------------------------------------------------------------ 端口

def free(port: int, udp: bool = False) -> bool:
    """试绑一下，能绑就是空闲。

    比读 netstat 可靠：netstat 里 TIME_WAIT 之类的状态会误导判断，
    而真正决定「能不能起来」的就是 bind 本身。
    """
    fam = socket.AF_INET
    typ = socket.SOCK_DGRAM if udp else socket.SOCK_STREAM
    s = socket.socket(fam, typ)
    try:
        if not udp:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0" if not udp else "127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class Child:
    def __init__(self, tag: str, cmd: list[str], fatal_codes: tuple[int, ...] = (2,)):
        self.tag = tag
        self.cmd = cmd
        self.fatal_codes = fatal_codes
        self.proc: subprocess.Popen | None = None
        self.starts: list[float] = []
        self.dead = False
        self.exited_normally = False

    @property
    def label(self) -> str:
        return f"[{self.tag:<6}]"

    def start(self) -> bool:
        color = TAG_COLOR.get(self.tag, "")
        try:
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as e:
            self.say(f"{RED}启动失败：{e}{RESET}")
            self.dead = True
            return False
        self.starts.append(time.monotonic())
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def say(self, msg: str) -> None:
        print(f"{TAG_COLOR.get(self.tag, '')}{self.label}{RESET} {msg}", flush=True)

    def _pump(self) -> None:
        """把子进程的每一行加上标签转发到本窗口。"""
        p = self.proc
        if not p or not p.stdout:
            return
        for raw in p.stdout:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            # 子进程自己带颜色的行保留原色，只在前面加标签
            print(f"{TAG_COLOR.get(self.tag, '')}{self.label}{RESET} {line}", flush=True)

    def poll(self) -> None:
        if self.dead or self.proc is None:
            return
        code = self.proc.poll()
        if code is None:
            return
        if self.exited_normally:
            return

        # 清掉已经过期的重启记录
        now = time.monotonic()
        self.starts = [t for t in self.starts if now - t < RESTART_WINDOW]

        if code in self.fatal_codes:
            self.say(f"{RED}已退出（代码 {code}），这是配置/环境问题，不重试。{RESET}")
            self.dead = True
            return

        if len(self.starts) >= MAX_RESTART:
            self.say(f"{RED}反复退出（{len(self.starts)} 次），停止重拉。{RESET}")
            self.say(f"{RED}看它上面的最后几行报错。{RESET}")
            self.dead = True
            return

        self.say(f"{YELLOW}退出（代码 {code}），2 秒后重拉…{RESET}")
        time.sleep(2.0)
        self.start()

    def stop(self, grace: float = 2.5) -> None:
        """等它自己退，超时才强杀。留时间给 vjoy_out 把杆回中。"""
        self.exited_normally = True
        p = self.proc
        if p is None or p.poll() is not None:
            return
        try:
            p.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self.say(f"{YELLOW}没有按时退出，强制结束{RESET}")
            p.terminate()
            try:
                p.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="多端 DCS 外设 · 一键启动")
    ap.add_argument("--port", type=int, default=8080, help="桥接 HTTP 端口")
    ap.add_argument("--udp-in", type=int, default=5010, help="遥测 UDP 入口端口")
    ap.add_argument("--mock", action="store_true",
                    help="额外启动 60Hz 假遥测（有真 DCS 时别开）")
    ap.add_argument("--no-vjoy", action="store_true", help="不启动虚拟摇杆输出")
    ap.add_argument("--no-usb", action="store_true",
                    help="跳过手机/USB 隧道检查（只跑桥接与摇杆输出）")
    ap.add_argument("--vjoy-port", type=int, default=5011,
                    help="操纵量内部转发端口")
    args = ap.parse_args()

    py = sys.executable or "python"

    print()
    print("═" * 70)
    print(f"  {BOLD}多端 DCS 外设 · 启动器{RESET}")
    print("═" * 70)

    # ---- 1. 手机与 adb ----
    if not args.no_usb:
        print("  [1/3] 检查 adb 与手机 …")
        adb = find_adb()
        if not adb:
            print(f"  {RED}[x]{RESET} 找不到 adb。")
            print(f"      预期位置：%LOCALAPPDATA%\\Android\\Sdk\\platform-tools\\adb.exe")
            print(f"      装 Android Studio，或把 platform-tools 加进 PATH。")
            print(f"      {DIM}只想跑桥接试试？加 --no-usb{RESET}")
            return 2
        serial, state = wait_device(adb)
        if not serial:
            why = {
                "unauthorized": "手机没授权 —— 在手机上点「允许 USB 调试」",
                "offline": "设备离线 —— 换根数据线或重插一次",
                "none": "没检测到设备 —— 确认是数据线不是充电线，且 USB 调试已开",
            }.get(state, f"设备状态 {state}")
            print(f"  {RED}[x]{RESET} 20 秒内没等到可用设备：{why}")
            for s, st in list_devices(adb):
                print(f"      {s}  {st}")
            print(f"      {DIM}adb = {adb}{RESET}")
            return 2
        print(f"        {GREEN}✓{RESET} 设备 {serial}")

        print("  [2/3] 建立 USB 隧道 …")
        if setup_tunnel(adb, args.port):
            print(f"        {GREEN}✓{RESET} tcp:{args.port} -> tcp:{args.port}")
        else:
            # 不中止：usb-watchdog 每 2 秒会重建一次隧道，几秒后自己就好。
            # 为了一个会被自动修好的问题挡住整个启动，只会让人多排查一轮。
            print(f"        {YELLOW}[!]{RESET} 这次没建起来，看守进程会在几秒内自动重试")
            print(f"            {DIM}如果一直连不上，拔插一次手机{RESET}")
    else:
        print(f"  {DIM}[1-2/3] 已跳过手机/USB 检查（--no-usb）{RESET}")

    # ---- 端口预检：上次没退干净是启动失败最常见的原因 ----
    busy = []
    if not free(args.port):
        busy.append(f"TCP {args.port}（桥接）")
    if not args.no_vjoy and not free(args.vjoy_port, udp=True):
        busy.append(f"UDP {args.vjoy_port}（虚拟摇杆）")
    if busy:
        print(f"  {RED}[x]{RESET} 端口被占用：{'、'.join(busy)}")
        print(f"      上一次的窗口多半还没关。找到它关掉，或者重启一次电脑。")
        print()
        return 2

    children: list[Child] = []
    children.append(Child("beacon", [
        py, "-u", os.path.join("tools", "beacon.py"),
        "--port", str(args.port), "--ipv4-only", "--udp-in", str(args.udp_in),
    ]))
    children.append(Child("watch", [
        py, "-u", os.path.join("tools", "usb-watchdog.py"),
        "--port", str(args.port), "--interval", "2",
    ]))
    if not args.no_vjoy:
        children.append(Child("vjoy", [
            py, "-u", os.path.join("tools", "vjoy_out.py"),
            "--port", str(args.vjoy_port),
            "--report", f"http://127.0.0.1:{args.port}",
        ]))
    if args.mock:
        children.append(Child("mock", [
            py, "-u", os.path.join("tools", "mock_export.py"),
            "--profile", "maneuver", "--rate", "60",
        ]))

    print("  [3/3] 启动服务 …")
    for c in children:
        c.start()

    print()
    print(f"  {GREEN}[✓]{RESET} 已启动 {len(children)} 个服务。"
          f"手机摇杆页顶部应显示「虚拟摇杆就绪」。")
    print(f"  {DIM}Ctrl+C 或关闭本窗口 = 全部停止（会先让杆回中）。{RESET}")
    print("═" * 70)
    print()

    try:
        while True:
            time.sleep(0.4)
            for c in children:
                c.poll()
            if all(c.dead or (c.proc and c.proc.poll() is not None) for c in children):
                print(f"\n  {RED}所有服务都已退出。{RESET}")
                break
    except KeyboardInterrupt:
        print(f"\n  {DIM}正在停止…{RESET}")

    for c in children:
        c.stop()
    print(f"  {GREEN}[✓]{RESET} 已全部停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vjoy_out.py — 把手机发来的操纵量写进虚拟摇杆

链路：
    手机倾斜传感器 ──HTTP POST /input──> beacon.py
                                          │ UDP 127.0.0.1:5011
                                          ▼
                                    本进程 ──vJoy──> DCS

为什么单独一个进程，而不是塞进 beacon.py：
    vJoy 驱动是最脆弱的一环（驱动没装、设备被占用、DLL 位数不对）。
    让它和遥测桥接共用一个进程，等于「杆出问题顺带把仪表也弄瞎」。
    拆开以后，vjoy_out 挂了可以单独重启，仪表不受影响。

═══════════════════════════════════════════════════════════════════
安全：这个脚本最重要的一段不是转发，是「怎么保证不失控」
═══════════════════════════════════════════════════════════════════
vJoy 是**状态保持**的：写入 16000 之后，即使写它的进程被杀掉，
这个值也会一直留在驱动里。也就是说如果本进程被强杀、崩溃、或者
手机突然断连，飞机就会保持住最后那个舵量一直转下去 —— 在 DCS 里
这基本等于摔机。

所以做了三层：
  1. 看门狗：超过 --timeout（默认 500ms）没收到新操纵量，立刻回中。
  2. 退出归零：Ctrl+C / 关窗口 / 注销 都会先 ResetVJD 再释放设备。
  3. 兜底命令行：`python tools/vjoy_out.py --reset` 一键回中退出，
     万一上面两层都没来得及跑，用这个捞回来。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time
from ctypes import wintypes

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)

# vJoy 的轴编号用的是 HID Usage ID，不是「第几根轴」。
AXIS = {"x": 0x30, "y": 0x31, "z": 0x32, "rx": 0x33, "ry": 0x34, "rz": 0x35,
        "sl0": 0x36, "sl1": 0x37}

VJD_STAT = {0: "已被本进程占用", 1: "空闲可用", 2: "被别的程序占用",
            3: "设备不存在（没在 vJoyConf 里启用）", 4: "未知"}

CENTER = 16384          # vJoy 轴中点。范围 1..32767，不是 0..32767
HALF = 16383


# ------------------------------------------------------------------ DLL

def _candidates() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [
        r"C:\Program Files\vJoy",
        r"C:\Program Files (x86)\vJoy",
        r"D:\vJoy",
        here,
        os.path.join(here, "..", "vendor", "vjoy"),
    ]
    out = []
    for r in roots:
        for sub in ("x64", ""):
            out.append(os.path.join(r, sub, "vJoyInterface.dll"))
    out.append(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                            "System32", "vJoyInterface.dll"))
    return [os.path.normpath(p) for p in out]


def load_vjoy():
    """按候选路径挨个 loadlib。

    不用 pip 的 pyvjoy：它把 DLL 打进 wheel 里，版本和本机驱动对不上时
    报的错是「模块加载失败」，看不出到底缺什么。自己 loadlib 至少能
    把「试过哪些路径」原样打出来。
    """
    tried = []
    for p in _candidates():
        if not os.path.isfile(p):
            continue
        try:
            return ctypes.WinDLL(p), p
        except OSError as e:
            tried.append(f"{p} -> {e}")
    if tried:
        raise RuntimeError("找到 vJoyInterface.dll 但加载失败：\n    " + "\n    ".join(tried))
    raise RuntimeError(
        "找不到 vJoyInterface.dll。装一次 vJoy 即可：\n"
        "    安装包在 .tmp/vjoy/vJoySetup.exe（右键 → 以管理员身份运行）\n"
        "    装完在开始菜单搜 “Configure vJoy”，确认 Device 1 已启用"
    )


class VJoy:
    def __init__(self, dev_id: int = 1):
        self.dll, self.path = load_vjoy()
        self.id = dev_id
        d = self.dll

        d.vJoyEnabled.restype = wintypes.BOOL
        d.vJoyEnabled.argtypes = []
        d.GetvJoyVersion.restype = ctypes.c_short
        d.GetvJoyVersion.argtypes = []
        d.GetvJoyProductString.restype = ctypes.c_wchar_p
        d.GetvJoyProductString.argtypes = []
        d.isVJDExists.restype = wintypes.BOOL
        d.isVJDExists.argtypes = [ctypes.c_uint]
        d.GetVJDStatus.restype = ctypes.c_int
        d.GetVJDStatus.argtypes = [ctypes.c_uint]
        d.AcquireVJD.restype = wintypes.BOOL
        d.AcquireVJD.argtypes = [ctypes.c_uint]
        d.RelinquishVJD.restype = None
        d.RelinquishVJD.argtypes = [ctypes.c_uint]
        d.SetAxis.restype = wintypes.BOOL
        d.SetAxis.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_uint]
        d.ResetVJD.restype = wintypes.BOOL
        d.ResetVJD.argtypes = [ctypes.c_uint]

    def check(self) -> None:
        if not self.dll.vJoyEnabled():
            raise RuntimeError(
                "vJoy 驱动没在运行。装完 vJoy 后需要重启一次，\n"
                "    然后在开始菜单搜 “Configure vJoy” 启用 Device 1。"
            )
        ver = self.dll.GetvJoyVersion()
        if not self.dll.isVJDExists(self.id):
            raise RuntimeError(
                f"vJoy 驱动在跑（v{ver >> 8}.{ver & 0xFF} 接口），但 Device {self.id} 不存在。\n"
                f"    打开 “Configure vJoy” → 勾上 Device 1 → 至少启用 X、Y 两根轴 → Apply"
            )
        st = self.dll.GetVJDStatus(self.id)
        if st == 1 and not self.dll.AcquireVJD(self.id):
            raise RuntimeError(f"Device {self.id} 拿不到（状态：{VJD_STAT.get(st)}）")
        if st == 2:
            raise RuntimeError(
                f"Device {self.id} 被别的程序占用了（{VJD_STAT.get(st)}）。\n"
                "    常见原因：上一次的 vjoy_out.py 没退干净，或者 vJoyConf 还开着。"
            )
        if st == 3:
            raise RuntimeError(f"Device {self.id} 不存在：{VJD_STAT.get(st)}")
        self.acquired = True

    def axis(self, aid: int, value: int) -> None:
        # 1..32767 之外的值 vJoy 会直接拒收，clamp 掉免得静默失败
        v = 1 if value < 1 else (32767 if value > 32767 else value)
        self.dll.SetAxis(v, self.id, aid)

    def reset(self) -> None:
        try:
            self.dll.ResetVJD(self.id)
        except Exception:
            pass

    def release(self) -> None:
        try:
            self.dll.RelinquishVJD(self.id)
        except Exception:
            pass


# ------------------------------------------------------------------ 心跳

def heartbeat_loop(url: str, info: dict, stop: threading.Event) -> None:
    """每秒向桥接报一次活。

    用原生 http.client 而不是 requests：只用一次的东西不值得多一个依赖，
    而且这里必须能设很短的超时 —— 心跳卡住不能拖累主循环（它在独立线程）。
    """
    import http.client
    from urllib.parse import urlparse

    u = urlparse(url)
    host = u.hostname or "127.0.0.1"
    port = u.port or 80
    path = (u.path or "") + "/vjoy"
    body = json.dumps(info).encode()

    conn = None
    while not stop.is_set():
        try:
            if conn is None:
                conn = http.client.HTTPConnection(host, port, timeout=1.0)
            conn.request("POST", path, body=body,
                         headers={"Content-Type": "application/json"})
            conn.getresponse().read()
            info["ok"] = True
        except Exception as e:
            info["ok"] = False
            info["msg"] = f"{info.get('msg', '')} / 心跳失败: {e}"[:200]
            try:
                conn.close()
            except Exception:
                pass
            conn = None
        stop.wait(1.0)


# ------------------------------------------------------------------ 干跑

class DryDevice:
    """不碰驱动的假设备，用来在没装 vJoy 的机器上验证接收链路。

    它记录最后写入的值，并在每秒的状态行里显示，这样「手机推杆 → 桥接
    转发 → 这里收到并换算成轴值」整条路径都能在没有驱动的情况下确认。
    真机上唯一没被覆盖的就剩 VJoy.axis 那三行 ctypes 调用。
    """

    path = "(dry-run)"

    def __init__(self):
        self.values: dict[int, int] = {}

    def axis(self, aid: int, value: int) -> None:
        v = 1 if value < 1 else (32767 if value > 32767 else value)
        self.values[aid] = v

    def reset(self) -> None:
        self.values.clear()

    def release(self) -> None:
        pass


# ------------------------------------------------------------------ 主循环

def to_axis(v: float) -> int:
    """-1..+1 → 1..32767，中点精确落在 CENTER。"""
    v = max(-1.0, min(1.0, v))
    return int(round(CENTER + v * HALF))


def run(args) -> int:
    dry = args.dry_run
    if dry:
        # 没有 vJoy 驱动时也能验完整条接收链路（收包、裁剪、看门狗、心跳）。
        # 装上驱动以后，未知的只剩「驱动那三行 ctypes 调用」。
        dev = DryDevice()
        where = "DRY-RUN（不输出到驱动）"
    else:
        try:
            dev = VJoy(args.id)
            dev.check()
        except RuntimeError as e:
            print(f"\n  {RED}[x]{RESET} {e}\n")
            return 2
        where = f"vJoyInterface = {dev.path}"

    print()
    print("═" * 62)
    print(f"  虚拟摇杆输出   Device {args.id}   {where}")
    print("═" * 62)
    print(f"  监听 UDP 127.0.0.1:{args.port}   X<-{args.map_x}  Y<-{args.map_y}")
    print(f"  看门狗 {args.timeout} ms 无消息自动回中")
    if args.report:
        print(f"  心跳 -> {args.report}/vjoy")
    print(f"  {DIM}Ctrl+C 退出（会先回中）。救急：python tools/vjoy_out.py --reset{RESET}")
    print()

    # 退出路径必须比正常路径更可靠。Ctrl+C 用 signal，关窗口/注销用
    # SetConsoleCtrlHandler —— 后者 Python 的 signal 接不到。
    _done = {"v": False}

    def cleanup(*_a):
        if _done["v"]:
            return False
        _done["v"] = True
        dev.reset()
        dev.release()
        print(f"\n  {GREEN}[✓]{RESET} 已回中并释放 Device {args.id}")
        return False

    import atexit
    import signal
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda *a: sys.exit(cleanup() or 0))
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(cleanup() or 0))
    try:
        _CTRL_TYPE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
        _cb = _CTRL_TYPE(lambda ev: cleanup())      # 返回 False = 交回默认处理
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_cb, True)
        # 不持有引用的话 _cb 会被 GC 掉，驱动里的回调地址就悬空了
        globals()["_CTRL_CB"] = _cb
    except Exception:
        pass

    hb_stop = threading.Event()
    if args.report and args.report.lower() != "none":
        info = {"ok": True, "msg": f"Device {args.id} {'dry-run' if dry else 'vJoy'}"}
        threading.Thread(
            target=heartbeat_loop, args=(args.report, info, hb_stop), daemon=True
        ).start()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", args.port))
    except OSError as e:
        print(f"  {RED}[x]{RESET} UDP {args.port} 绑定失败：{e}")
        cleanup()
        return 2
    s.settimeout(0.02)          # 20ms 超时 = 看门狗检查粒度

    dev.reset()
    last_rx = 0.0
    centered = True
    n = 0
    last_stat = 0.0
    last_n = 0

    while True:
        try:
            data, _ = s.recvfrom(2048)
        except socket.timeout:
            data = None
        except OSError:
            break

        now = time.time()

        if data:
            try:
                obj = json.loads(data.decode("utf-8", "replace"))
                x = float(obj.get("x", 0.0))
                y = float(obj.get("y", 0.0))
            except Exception:
                x = y = 0.0
            if x != x: x = 0.0        # NaN
            if y != y: y = 0.0
            if args.invert_x: x = -x
            if args.invert_y: y = -y
            dev.axis(AXIS[args.map_x], to_axis(x))
            dev.axis(AXIS[args.map_y], to_axis(y))
            last_rx = now
            n += 1
            centered = False

        elif not centered and (now - last_rx) * 1000.0 >= args.timeout:
            # 只在「从有到无」的那一次写中位，不要每 20ms 反复写 ——
            # 驱动调用本身有开销，50Hz 的驱动写对 DCS 的轴采样也没有帮助
            dev.axis(AXIS[args.map_x], CENTER)
            dev.axis(AXIS[args.map_y], CENTER)
            centered = True
            print(f"\r  {YELLOW}[!]{RESET} {(now - last_rx) * 1000:.0f} ms 无消息 → 已回中"
                  f"{' ' * 30}")

        if now - last_stat >= 2.0:
            # 用**窗口内**的增量算速率。用累计数除以总时长会得到一个
            # 只降不升的平均值，空转时一路衰减到 0，看起来像链路挂了。
            hz = (n - last_n) / max(0.001, now - last_stat)
            last_stat = now
            last_n = n
            state = f"{DIM}等待手机{RESET}" if n == 0 else (
                f"{DIM}已回中{RESET}" if centered else f"{GREEN}跟随中{RESET}")
            extra = ""
            if dry:
                xv = dev.values.get(AXIS[args.map_x], CENTER)
                yv = dev.values.get(AXIS[args.map_y], CENTER)
                extra = (f"  X={xv:5d} ({(xv - CENTER) / HALF:+.2f})"
                         f"  Y={yv:5d} ({(yv - CENTER) / HALF:+.2f})")
            print(f"\r  {state}  {n} 包  {hz:.0f} Hz{extra}{' ' * 12}", end="")

    s.close()
    hb_stop.set()
    cleanup()
    return 0


def hard_reset(dev_id: int) -> int:
    try:
        dev = VJoy(dev_id)
    except RuntimeError as e:
        print(f"  {RED}[x]{RESET} {e}")
        return 2
    dev.reset()
    dev.release()
    print(f"  {GREEN}[✓]{RESET} Device {dev_id} 已回中并释放")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="多端 DCS 外设 · 虚拟摇杆输出")
    ap.add_argument("--id", type=int, default=1, help="vJoy 设备号（默认 1）")
    ap.add_argument("--port", type=int, default=5011, help="收操纵量的 UDP 端口")
    ap.add_argument("--map-x", default="x", choices=sorted(AXIS),
                    help="手机横向倾斜映射到 vJoy 哪根轴")
    ap.add_argument("--map-y", default="y", choices=sorted(AXIS),
                    help="手机前后倾斜映射到 vJoy 哪根轴")
    ap.add_argument("--invert-x", action="store_true")
    ap.add_argument("--invert-y", action="store_true")
    ap.add_argument("--timeout", type=int, default=500,
                    help="多少毫秒没消息就回中（默认 500）")
    ap.add_argument("--report", default="http://127.0.0.1:8080",
                    help="每秒向桥接报一次活，让手机端能看到虚拟摇杆是否就绪"
                         "（给 none 关闭）")
    ap.add_argument("--dry-run", action="store_true",
                    help="不连 vJoy 驱动，只验证收包与看门狗逻辑")
    ap.add_argument("--reset", action="store_true",
                    help="只回中并释放设备，然后退出（救急用）")
    args = ap.parse_args()

    if args.reset:
        return hard_reset(args.id)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

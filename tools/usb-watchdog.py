#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
usb-watchdog.py — 让 `adb reverse` 永不丢失

为什么需要它：
    `adb reverse` 的规则存在 adb 服务进程的内存里。adb 服务一旦重启
    （手机拔插、USB 模式切换、adb 被别的工具重启、系统休眠唤醒），
    规则就没了。表现是手机 App 突然「连接失败」，但 PC 上什么都正常，
    非常难排查。

它做什么：
    每 2 秒检查一次 `adb reverse --list`，发现 `tcp:8080` 不在了就立刻重加。
    同时每 30 秒打印一次心跳（设备在不在、数据有多旧），方便判断问题出在哪。

用法：
    python tools/usb-watchdog.py
    python tools/usb-watchdog.py --port 8080 --interval 2

退出：Ctrl+C
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_adb() -> str | None:
    """优先用 SDK 里的 adb，其次 PATH 里的。"""
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    for c in candidates:
        if c.exists():
            return str(c)
    # PATH 兜底
    for p in os.environ.get("PATH", "").split(os.pathsep):
        exe = Path(p) / ("adb.exe" if os.name == "nt" else "adb")
        if exe.exists():
            return str(exe)
    return None


def run(adb: str, *args: str, timeout: float = 8) -> str:
    try:
        p = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
        raw = p.stdout or b""
    except Exception:
        return ""
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def device_online(adb: str) -> tuple[bool, str]:
    out = run(adb, "devices")
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] and re.fullmatch(r"[\w.:-]+", parts[0]):
            if parts[1] == "device":
                return True, parts[0]
            if parts[1] == "unauthorized":
                return False, "unauthorized"
    return False, "none"


def reverse_present(adb: str, port: int) -> bool:
    out = run(adb, "reverse", "--list")
    return f"tcp:{port}" in out


def ensure_reverse(adb: str, port: int) -> bool:
    out = run(adb, "reverse", f"tcp:{port}", f"tcp:{port}")
    ok = reverse_present(adb, port)
    if ok:
        return True
    sys.stderr.write(f"  [!] reverse 建立失败：{out.strip()}\n")
    return False


# 空 ProxyHandler = 不走任何代理，直连
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def bridge_state(port: int) -> tuple[bool, bool, int | None, float, str]:
    """问桥接服务要一次状态。

    返回 (连得上?, 有数据?, age_ms, hz, 错误原因)。

    为什么要把「连不上」和「没数据」分开：这两件事的处理方式完全相反。
    连不上 = USB 隧道/桥接进程有问题；没数据 = 桥接好好的，只是 DCS 没开。
    早期版本用一个 `age is None` 同时表示两者，于是只要没开 DCS，看守就会
    喊「桥接服务未响应」—— 一个纯假警报，还把人往错的方向带。

    **必须绕过系统代理**：这台机器上开了 HTTP 代理，`urllib` 默认会把发往
    127.0.0.1 的请求也交给代理，代理不知道本机 8080 是什么，直接失败。
    """
    try:
        with _OPENER.open(f"http://127.0.0.1:{port}/state", timeout=2) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        return False, False, None, 0.0, f"{type(e).__name__}: {e}"
    stats = d.get("stats") or {}
    return (
        True,
        bool(d.get("has_data")),
        stats.get("age_ms"),
        float(stats.get("hz") or 0),
        "",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="保持 adb reverse 存活")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--quiet", action="store_true", help="不打心跳，只在修好时输出")
    args = ap.parse_args()

    adb = find_adb()
    if not adb:
        print("[x] 找不到 adb。请确认 Android SDK 已安装。")
        return 1

    print()
    print("═" * 62)
    print("  USB 通道看守")
    print("═" * 62)
    print(f"  adb      {adb}")
    print(f"  端口     tcp:{args.port}")
    print(f"  轮询     {args.interval:g}s    Ctrl+C 退出")
    print("═" * 62)
    print()

    last_reverse_ok = False
    last_heartbeat = 0.0
    fixes = 0

    try:
        while True:
            online, info = device_online(adb)

            if online:
                has = reverse_present(adb, args.port)
                if not has:
                    if ensure_reverse(adb, args.port):
                        fixes += 1
                        print(f"  [{datetime.now():%H:%M:%S}] 转发丢失，已重建（累计 {fixes} 次）")
                    last_reverse_ok = True
                else:
                    if not last_reverse_ok:
                        print(f"  [{datetime.now():%H:%M:%S}] 转发正常，设备 {info}")
                    last_reverse_ok = True
            else:
                if last_reverse_ok or info == "unauthorized":
                    reason = "未授权（手机上点允许）" if info == "unauthorized" else "无设备"
                    print(f"  [{datetime.now():%H:%M:%S}] 设备不可用：{reason}")
                last_reverse_ok = False

            now = time.time()
            if not args.quiet and now - last_heartbeat >= 30:
                last_heartbeat = now
                reachable, has_data, age, hz, err = bridge_state(args.port)
                if not reachable:
                    stat = f"桥接服务未响应（{err}）"
                elif has_data:
                    stat = f"数据正常 age={age}ms {hz:.1f}Hz"
                elif age is None:
                    stat = "桥接在线，但还没收到过遥测（DCS 没开 / 不在任务里 / mock 没运行）"
                else:
                    stat = f"遥测中断 age={age}ms（DCS 退出了？）"
                print(f"  [{datetime.now():%H:%M:%S}] 心跳：{stat}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n  已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

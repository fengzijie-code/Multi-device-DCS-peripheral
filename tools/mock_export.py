#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mock_export.py — 多端 DCS 外设 · P0 遥测模拟源

作用：在没有 DCS 的机器上，按 `Export.lua` **完全相同的线格式**往本机 UDP 发遥测。
这样协议层、桥接服务、客户端 UI、性能测试全部可以脱离 DCS 开发和回归。

用法：
    python tools/mock_export.py                    # 60 Hz 发到 127.0.0.1:5010
    python tools/mock_export.py --profile maneuver --rate 30
    python tools/mock_export.py --duration 60      # 跑 60 秒后自动退出
    python tools/mock_export.py --nan              # 故意混入 NaN / Inf
    python tools/mock_export.py --drop 0.05        # 模拟 5% 丢包
    python tools/mock_export.py --stall 10         # 每 10 秒卡住 1 秒

线格式（P0 阶段用 JSON 行，P1 会换成 protobuf）：
    {"t": 12.345, "alt": 1520.3, "agl": 420.1, "ias": 245.1, "gs": 310.0,
     "vs": 2.1, "pitch": -0.02, "bank": 0.11, "hdg": 1.234, "g": 1.0, "mach": 0.42}

另外每秒单独发一包**慢变量**（和 Export.lua 同格式），给 iPad 辅助面板用：
    {"sys": {"t":.., "fuel":.., "fuelx":.., "rpm_l":.., "rpm_r":..,
             "temp_l":.., "temp_r":.., "hyd_l":.., "hyd_r":..,
             "canopy":.., "wbrake":.., "cs_a":.., "cs_e":.., "cs_r":..}}

字段与 DCS 导出的对应关系：
    alt  ← LoGetAltitudeAboveSeaLevel()    米
    agl  ← LoGetAltitudeAboveGroundLevel() 米
    ias  ← LoGetIndicatedAirSpeed()        米/秒
    gs   ← LoGetTrueAirSpeed() 近似        米/秒
    vs   ← LoGetVerticalVelocity()         米/秒
    pitch/bank/hdg ← LoGetSelfData()       弧度
    g    ← LoGetAccelerationUnits().y      G
    fuel/fuelx ← LoGetEngineInfo()         公斤（**不是** 0–1 的比例）
"""

from __future__ import annotations

import argparse
import json
import math
import random
import socket
import sys
import time
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 飞行剖面

class FlightModel:
    """一个够用就好的飞行剖面生成器。

    不追求气动正确，只要求：数值之间的相关性合理、变化率符合直觉、
    能让 UI 的指针插值和刻度滚动被真实地考验到。
    """

    def __init__(self, profile: str, seed: int | None = None, aircraft: str = "full"):
        self.profile = profile
        self.aircraft = aircraft
        self.rng = random.Random(seed)
        self.t0 = time.perf_counter()

    def sample(self, t: float) -> dict:
        alt, agl, ias, pitch, bank, g = self._core(t)

        # vs 由高度差分数值求导，保证与 alt 永远自洽。
        # 如果两者各算一套，UI 上会出现「高度在涨但升降率为负」的假象，
        # 回归测试会照着假象写错断言。
        dt = 0.05
        alt_ahead = self._core(t + dt)[0]
        vs = (alt_ahead - alt) / dt

        # 噪声用绝对值而不是百分比：8000 米高度上 0.4% 就是 ±32 米抖动，
        # 会让高度带看起来像在做高频振动，那是假象。
        j = self.rng.uniform
        return {
            "t": round(t, 3),
            "alt": round(alt + j(-0.5, 0.5), 2),
            "agl": round(agl + j(-0.5, 0.5), 2),
            "ias": round(ias + j(-0.3, 0.3), 2),
            "gs": round(ias * 1.28 + j(-0.4, 0.4), 2),
            "vs": round(vs + j(-0.05, 0.05), 2),
            "pitch": round(pitch + j(-0.002, 0.002), 5),
            "bank": round(bank + j(-0.003, 0.003), 5),
            "hdg": round(self._norm_hdg(0.6 + 0.35 * math.sin(t / 55)), 5),
            "g": round(max(0.0, g + j(-0.03, 0.03)), 2),
            "mach": round(ias / 295.0, 3),

            # 扩展字段：模拟 DCS 探针实测出的结构（RPM/Temperature 是左右两个值）
            "aoa": round(pitch * 0.85 + 0.015, 4),
            "rpm_l": round(84 + 6 * math.sin(t / 30) + j(-0.4, 0.4), 1),
            "rpm_r": round(84 + 6 * math.sin(t / 30 + 0.05) + j(-0.4, 0.4), 1),
            "temp_l": round(560 + 90 * abs(math.sin(t / 30)) + j(-3, 3), 1),
            "temp_r": round(560 + 90 * abs(math.sin(t / 30 + 0.05)) + j(-3, 3), 1),
            # 燃油单位必须是 kg（真实 DCS 的 fuel_internal 就是 kg，上千的量级）。
            # 这里曾经写成 0–1 的比例，面板上油量条和消耗率就全是假数 ——
            # 模拟源和真实导出对不上，脱离 DCS 做的一切验证都没有意义。
            "fuel": round(max(0.0, 3200.0 - t * 1.15), 2),
            "fuelx": 0.0,
            "gear": 0.0 if alt > 50 else 1.0,
            "flaps": 0.0,
            "sbrk": 0.0,
            "shells": 510,
        }

    def sys_fields(self, t: float) -> dict:
        """慢变量包的内容（1Hz，独立于 60Hz 主帧单独发）。

        取值刻意保持在机坪/爬升都说得通的范围内，方便肉眼判断面板有没有
        串行。`cs_e` 里那个 0.020 弧度是**配平偏置**：面板的配平估读就是
        在杆回中时取这个值，源码里带一点偏置才验得出「采样/保持」逻辑。
        """
        # TF-51D（实测的真实形态）：单发、没有温度/液压/座舱盖/舵面偏度，
        # 燃油给的是 0–1 比例而不是公斤。这条分支存在的意义是：以后改面板
        # 时能随时回归「字段缺失」这个场景，不用真去开一架野马。
        if self.aircraft == "tf51":
            return {
                "t": round(t, 2),
                "fuel": round(max(0.0, 0.986 - t * 0.0002), 4),
                "fuelx": None,
                "rpm_l": round(85.7 + 0.4 * math.sin(t / 20), 1),
                "rpm_r": None,
                "temp_l": None,
                "temp_r": None,
                "hyd_l": None,
                "hyd_r": None,
                "canopy": None,
                "wbrake": None,
                "cs_a": None,
                "cs_e": None,
                "cs_r": None,
            }
        return {
            "t": round(t, 2),
            "fuel": round(max(0.0, 3200.0 - t * 1.15), 2),
            "fuelx": 0.0,
            "rpm_l": round(84 + 6 * math.sin(t / 30), 1),
            "rpm_r": round(84 + 6 * math.sin(t / 30 + 0.05), 1),
            "temp_l": round(560 + 90 * abs(math.sin(t / 30)), 2),
            "temp_r": round(560 + 90 * abs(math.sin(t / 30 + 0.05)), 2),
            "hyd_l": 285.0,
            "hyd_r": 280.0,
            "canopy": 1.0,
            "wbrake": 0.0,
            # 舵面偏度，弧度。升降舵 = 配平偏置 0.020 + 慢波
            "cs_a": round(0.004 * math.sin(t / 7), 5),
            "cs_e": round(0.020 + 0.030 * math.sin(t / 9), 5),
            "cs_r": round(-0.004 * math.sin(t / 11), 5),
        }

    def _core(self, t: float):
        p = self.profile
        if p == "climb":
            return self._climb(t)
        if p == "cruise":
            return self._cruise(t)
        if p == "maneuver":
            return self._maneuver(t)
        if p == "ground":
            return self._ground(t)
        raise ValueError(f"未知剖面: {p}")

    # -- 各剖面 --------------------------------------------------

    def _climb(self, t: float):
        """起飞后持续爬升，180 秒到 9000 米。"""
        k = min(t / 180.0, 1.0)
        ease = k * k * (3 - 2 * k)                 # smoothstep，避免起止突兀
        alt = 500 + ease * 8500
        agl = max(alt - 300, 0)
        ias = 145 - 35 * ease                      # 越爬越慢
        pitch = 0.16 * (1 - 0.8 * ease)
        bank = 0.06 * math.sin(t / 9)
        return alt, agl, ias, pitch, bank, 1.05

    def _cruise(self, t: float):
        """平飞，带缓慢的高度漂移和轻微转弯。"""
        alt = 8000 + 40 * math.sin(t / 40)
        agl = alt - 600
        ias = 155 + 2 * math.sin(t / 13)
        pitch = 0.015 * math.sin(t / 70)
        bank = 0.35 * math.sin(t / 30)
        return alt, agl, ias, pitch, bank, 1.0

    def _maneuver(self, t: float):
        """剧烈机动：用来考验指针平滑与过载告警。"""
        bank = 1.05 * math.sin(t / 6)              # ±60°
        pitch = 0.35 * math.sin(t / 9 + 1.0)       # ±20°
        g = 1.0 + 4.5 * abs(math.sin(t / 6))       # 1–5.5 G
        alt = 4000 + 900 * math.sin(t / 20)
        agl = alt - 800
        ias = 210 + 30 * math.cos(t / 8)
        return alt, agl, ias, pitch, bank, g

    def _ground(self, t: float):
        """停机坪：几乎所有量都静止，用来验证 UI 在零变化时不抖。"""
        return 120.0, 120.0, 0.0, 0.0, 0.0, 1.0

    @staticmethod
    def _norm_hdg(v: float) -> float:
        return v % (2 * math.pi)


# ---------------------------------------------------------------- 发送

def main() -> int:
    ap = argparse.ArgumentParser(description="多端 DCS 外设 · 遥测模拟源")
    ap.add_argument("--target", default="127.0.0.1:5010", help="目标 host:port")
    ap.add_argument("--rate", type=float, default=60.0, help="发送频率 Hz")
    ap.add_argument("--profile", default="climb",
                    choices=["climb", "cruise", "maneuver", "ground"])
    ap.add_argument("--aircraft", default="full", choices=["full", "tf51"],
                    help="慢变量字段集：full 全量 / tf51 单发且缺字段（燃油给比例）")
    ap.add_argument("--duration", type=float, default=0, help="运行秒数，0 为不限")
    ap.add_argument("--nan", action="store_true", help="每 120 帧混入一个 NaN/Inf")
    ap.add_argument("--drop", type=float, default=0.0, help="模拟丢包率 0–1")
    ap.add_argument("--stall", type=float, default=0.0, help="每 N 秒卡住 1 秒")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    host, _, port_s = args.target.rpartition(":")
    if not host:
        host, port_s = "127.0.0.1", args.target
    try:
        port = int(port_s)
    except ValueError:
        print(f"[x] 端口不合法: {port_s}")
        return 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    model = FlightModel(args.profile, args.seed, args.aircraft)
    period = 1.0 / args.rate

    print()
    print("═" * 62)
    print("  遥测模拟源")
    print("═" * 62)
    print(f"  目标    {host}:{port}   频率 {args.rate:g} Hz   剖面 {args.profile}")
    if args.aircraft != "full":
        print(f"  机型    {args.aircraft}（缺字段 + 燃油比例）")
    if args.nan:
        print("  注入    NaN / Inf（用于验证桥接是否拒绝脏数据）")
    if args.drop:
        print(f"  丢包    {args.drop * 100:.0f}%")
    if args.stall:
        print(f"  卡顿    每 {args.stall:g} 秒停 1 秒")
    print(f"  开始    {datetime.now().strftime('%H:%M:%S')}    Ctrl+C 退出")
    print("═" * 62)
    print()

    t0 = time.perf_counter()
    next_tick = t0
    sent = dropped = nan_injected = sys_sent = 0
    last_report = t0
    last_sys = 0.0

    try:
        while True:
            now = time.perf_counter()
            elapsed = now - t0

            if args.duration and elapsed >= args.duration:
                break

            if now < next_tick:
                time.sleep(min(next_tick - now, 0.002))
                continue
            next_tick += period
            if next_tick < now - period * 5:      # 落后太多就别追了，重新对表
                next_tick = now + period

            # 模拟游戏侧卡顿：DCS 加载场景时会这样
            if args.stall and int(elapsed // args.stall) != int((elapsed - period) // args.stall):
                time.sleep(1.0)

            frame = model.sample(elapsed)

            # 慢变量：1Hz 单独一包，线格式与 Export.lua 完全一致（{"sys":{...}}）。
            # 放在丢包/脏值注入之前，让这两种故障只影响主帧 —— 慢变量卡住和
            # 主帧丢包是两个不同的故障，模拟的时候不能混在一起。
            if elapsed - last_sys >= 1.0:
                last_sys = elapsed
                sock.sendto(
                    json.dumps({"sys": model.sys_fields(elapsed)},
                               separators=(",", ":")).encode(),
                    (host, port),
                )
                sys_sent += 1

            if args.nan and sent % 120 == 119:
                key = ("alt", "ias", "pitch")[nan_injected % 3]
                frame[key] = float("nan") if nan_injected % 2 == 0 else float("inf")
                nan_injected += 1

            if args.drop and random.random() < args.drop:
                dropped += 1
                continue

            payload = json.dumps(frame, separators=(",", ":")).encode()
            try:
                sock.sendto(payload, (host, port))
            except OSError as e:
                print(f"\n[x] 发送失败: {e}")
                break
            sent += 1

            # 每秒打一行状态
            if now - last_report >= 1.0:
                last_report = now
                print(
                    f"  {elapsed:7.1f}s  "
                    f"alt {frame['alt']:7.1f}m  "
                    f"ias {frame['ias']:5.1f}m/s  "
                    f"bank {math.degrees(frame['bank']):+6.1f}°  "
                    f"G {frame['g']:4.2f}  "
                    f"已发 {sent}"
                    + (f"  丢 {dropped}" if dropped else "")
                )

    except KeyboardInterrupt:
        print()
    finally:
        sock.close()

    print()
    print(f"  结束：共发送 {sent} 帧" + (f"，模拟丢弃 {dropped} 帧" if dropped else "")
          + (f"，注入 {nan_injected} 个脏值" if nan_injected else "")
          + (f"，慢变量 {sys_sent} 包" if sys_sent else ""))
    print(f"  实际频率 {sent / max(time.perf_counter() - t0, 1e-6):.1f} Hz")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

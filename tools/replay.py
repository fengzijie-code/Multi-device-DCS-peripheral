#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replay.py — 把录制好的遥测按原始节奏重放给桥接服务

为什么需要它：
    改一行 UI 就要进一次 DCS，一轮五分钟。有了回放，同一段真实飞行可以反复喂给
    桥接服务和客户端，改完刷新就能看效果，不需要游戏、不需要起飞。

用法：
    python tools/replay.py                                  # 回放最新录制
    python tools/replay.py --file tests/fixtures/recording/climb.jsonl
    python tools/replay.py --speed 2                        # 2 倍速
    python tools/replay.py --loop                           # 循环播放，适合调 UI
    python tools/replay.py --max-gap 0.5                    # 超过 0.5s 的空档压缩掉

录制方式（由 beacon.py 提供）：
    python tools/beacon.py --record tests/fixtures/recording/climb.jsonl

文件格式：每行 {"w": <墙钟毫秒偏移>, "d": <原始遥测帧>}
"""

from __future__ import annotations

import argparse
import glob
import json
import socket
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
REC_DIR = ROOT / "tests" / "fixtures" / "recording"


def latest_recording() -> Path | None:
    files = sorted(glob.glob(str(REC_DIR / "*.jsonl")), key=lambda p: Path(p).stat().st_mtime)
    return Path(files[-1]) if files else None


def load(path: Path) -> tuple[list[dict], list[int]]:
    frames: list[dict] = []
    stamps: list[int] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                d = rec["d"]
                w = int(rec.get("w", 0))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            frames.append(d)
            stamps.append(w)
    return frames, stamps


def summarize(path: Path, frames: list[dict], stamps: list[int]) -> None:
    dur = (stamps[-1] - stamps[0]) / 1000 if stamps else 0
    hz = (len(frames) - 1) / dur if dur > 0 else 0
    alts = [f.get("alt", 0) for f in frames if isinstance(f.get("alt"), (int, float))]
    print()
    print("═" * 62)
    print("  遥测回放")
    print("═" * 62)
    print(f"  文件    {path}")
    print(f"  帧数    {len(frames)}")
    print(f"  时长    {dur:.1f} s   平均 {hz:.1f} Hz")
    if alts:
        print(f"  高度    {min(alts):.0f} – {max(alts):.0f} m")
    print("═" * 62)
    print()


def build_schedule(stamps: list[int], speed: float, max_gap: float) -> list[float]:
    """把墙钟毫秒序列换算成回放时间表（秒）。

    单独算一遍再逐帧照表发送，而不是边发边累加：
    边发边加会把发送耗时算进间隔里，长时间回放会越跑越慢。
    """
    out = [0.0]
    for i in range(1, len(stamps)):
        gap = (stamps[i] - stamps[i - 1]) / 1000.0 / speed
        if max_gap > 0 and gap > max_gap:
            gap = max_gap
        out.append(out[-1] + gap)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="回放录制的遥测")
    ap.add_argument("--file", default=None, help="jsonl 路径，默认取最新的一份")
    ap.add_argument("--target", default="127.0.0.1:5010")
    ap.add_argument("--speed", type=float, default=1.0, help="倍速，>1 更快")
    ap.add_argument("--loop", action="store_true", help="循环播放")
    ap.add_argument("--max-gap", type=float, default=0.0,
                    help="把超过该秒数的空档压缩成该值（0 表示保留原样）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    path = Path(args.file) if args.file else latest_recording()
    if not path or not path.exists():
        print("[x] 找不到录制文件。先跑：")
        print("    python tools/beacon.py --record tests/fixtures/recording/demo.jsonl")
        return 1

    frames, stamps = load(path)
    if not frames:
        print(f"[x] {path} 里没有可用帧")
        return 1

    summarize(path, frames, stamps)

    host, _, port_s = args.target.rpartition(":")
    if not host:
        host, port_s = "127.0.0.1", args.target
    port = int(port_s)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    schedule = build_schedule(stamps, args.speed, args.max_gap)
    sent = 0
    t0 = time.perf_counter()

    try:
        while True:
            start = time.perf_counter()
            for i, frame in enumerate(frames):
                wait = (start + schedule[i]) - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)

                payload = json.dumps(frame, separators=(",", ":")).encode()
                sock.sendto(payload, (host, port))
                sent += 1

                if not args.quiet and sent % 120 == 0:
                    el = time.perf_counter() - start
                    print(f"  {schedule[i]:6.1f}s  {sent:6d} 帧  "
                          f"alt {frame.get('alt', 0):7.0f}m")

            if not args.loop:
                break
            if not args.quiet:
                print("  —— 循环 ——")
            t0 = time.perf_counter()

    except KeyboardInterrupt:
        print()
    finally:
        sock.close()

    el = time.perf_counter() - t0
    print()
    print(f"  结束：发送 {sent} 帧，用时 {el:.1f}s（{args.speed:g}x）")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

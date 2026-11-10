#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_export_lua.py — 用嵌入式 Lua 跑真实的 dcs/Export.lua

为什么值得这么做：语法检查只能证明「能解析」，不能证明「发出去的 JSON 是对的、
字段顺序稳定、NaN 被清掉、节流有效」。这些恰恰是最容易错、也最难在 DCS 里
反复试的部分。

做法：起一个 Lua 运行时，注入假的 LoGet* / log / require("socket")，
加载真实的 Export.lua，调用导出钩子，把假 socket 收到的报文抓回 Python 校验。

依赖：pip install lupa

用法：
    python tests/test_export_lua.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import lupa
except ImportError:
    print("需要 lupa：python -m pip install lupa")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
EXPORT_LUA = ROOT / "dcs" / "Export.lua"

EXPECTED_FIELDS = ["t", "alt", "agl", "ias", "gs", "vs", "pitch", "bank", "hdg", "g", "mach"]


# ---------------------------------------------------------------- Lua 环境

LUA_PRELUDE = r"""
-- 抓包器：把 sendto 的报文塞进这个表
SENT = {}

-- 假 socket 模块
local fake_socket = {}
function fake_socket.udp()
    local s = {}
    function s:settimeout() end
    function s:setsockname() end
    function s:close() end
    function s:sendto(payload, host, port)
        SENT[#SENT + 1] = { payload = payload, host = host, port = port }
        return #payload
    end
    return s
end

-- 假 log
log = { INFO = 1, WARNING = 2, ERROR = 3 }
function log.write(tag, level, msg)
    LOGS = LOGS or {}
    LOGS[#LOGS + 1] = { level = level, msg = msg }
end

-- 假 require：只认 socket
function require(name)
    if name == "socket" then return fake_socket end
    error("no module: " .. tostring(name))
end

-- 可变的仿真状态，Python 侧通过 set_state 改
STATE = {
    t = 0.0,
    alt = 1520.25,
    agl = 420.5,
    ias = 244.75,
    tas = 312.5,
    vs = 2.25,
    pitch = -0.021,
    bank = 0.113,
    hdg = 1.2345,
    g = 1.02,
    mach = 0.42,
    nan_alt = false,
}

function set_state(k, v) STATE[k] = v end

function LoGetModelTime()     return STATE.t end
function LoGetSelfData()
    return { Pitch = STATE.pitch, Bank = STATE.bank, Heading = STATE.hdg, Name = "Test" }
end
function LoGetAltitudeAboveSeaLevel()
    if STATE.nan_alt then return 0/0 end
    return STATE.alt
end
function LoGetAltitudeAboveGroundLevel() return STATE.agl end
function LoGetIndicatedAirSpeed()        return STATE.ias end
function LoGetTrueAirSpeed()             return STATE.tas end
function LoGetVerticalVelocity()         return STATE.vs end
function LoGetMachNumber()               return STATE.mach end
function LoGetAccelerationUnits()        return { x = 0, y = STATE.g, z = 0 } end
"""


def make_runtime():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(LUA_PRELUDE)
    lua.execute(EXPORT_LUA.read_text(encoding="utf-8"))
    return lua


def sent(lua) -> list[dict]:
    """把 Lua 表里的报文取回 Python。"""
    tbl = lua.globals().SENT
    out = []
    for i in range(1, len(tbl) + 1):
        rec = tbl[i]
        out.append({
            "payload": rec["payload"],
            "host": rec["host"],
            "port": rec["port"],
        })
    return out


def reset(lua):
    lua.execute("SENT = {}")


# ---------------------------------------------------------------- 用例

class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []

    def check(self, name: str, cond: bool, detail: str = ""):
        if cond:
            self.passed += 1
            print(f"  \033[32m✓\033[0m {name}")
        else:
            self.failed += 1
            self.failures.append(name)
            print(f"  \033[31m✗\033[0m {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    print()
    print("=" * 60)
    print("  Export.lua 功能测试（嵌入式 Lua）")
    print("=" * 60)
    print()

    r = Result()
    lua = make_runtime()
    g = lua.globals()

    # --- T-EXPORT-001 正常帧 ---
    print("T-EXPORT-001 正常帧能发出合法 JSON")
    g.LuaExportStart()
    g.LuaExportAfterNextFrame()
    frames = sent(lua)
    r.check("发出 1 帧", len(frames) == 1, f"实际 {len(frames)}")
    if frames:
        try:
            obj = json.loads(frames[0]["payload"])
            r.check("可被 JSON 解析", True)
            r.check("字段完整且顺序稳定", list(obj.keys()) == EXPECTED_FIELDS,
                    f"实际 {list(obj.keys())}")
            r.check("alt 数值正确", abs(obj["alt"] - 1520.25) < 0.01, str(obj["alt"]))
            r.check("pitch 精度到 1e-5", abs(obj["pitch"] + 0.021) < 1e-5, str(obj["pitch"]))
            r.check("g 取自 AccelerationUnits.y", abs(obj["g"] - 1.02) < 0.01, str(obj["g"]))
        except json.JSONDecodeError as e:
            r.check("可被 JSON 解析", False, str(e))
        r.check("目标地址为回环", frames[0]["host"] == "127.0.0.1", frames[0]["host"])
        r.check("目标端口 5010", frames[0]["port"] == 5010, str(frames[0]["port"]))

    # --- T-EXPORT-002 时间冻住 ---
    print()
    print("T-EXPORT-002 仿真时间冻住时不得持续发送（防止暂停时刷屏）")
    reset(lua)
    for _ in range(10):
        g.LuaExportAfterNextFrame()          # t 不变
    first = len(sent(lua))
    reset(lua)
    for _ in range(10):
        g.LuaExportAfterNextFrame()
    second = len(sent(lua))
    r.check("首轮最多补 1 帧（突发配额）", first <= 1, f"实际 {first}")
    r.check("配额用完后完全停发", second == 0, f"实际 {second}")

    # --- T-EXPORT-003 时间推进 ---
    print()
    print("T-EXPORT-003 仿真时间推进后按 60Hz 恢复发送")
    reset(lua)
    t = 0.0
    for _ in range(60):
        t += 1 / 60
        g.set_state("t", t)
        g.LuaExportAfterNextFrame()
    n = len(sent(lua))
    r.check("60 帧间隔约发出 60 帧", 55 <= n <= 61, f"实际 {n}")

    # --- T-EXPORT-004 NaN ---
    print()
    print("T-EXPORT-004 NaN 必须被清成 0 并打 dirty 标记")
    reset(lua)
    g.set_state("nan_alt", True)
    g.set_state("t", t + 1.0)
    g.LuaExportAfterNextFrame()
    frames = sent(lua)
    r.check("发出 1 帧", len(frames) == 1, f"实际 {len(frames)}")
    if frames:
        raw = frames[0]["payload"]
        r.check("报文不含 nan/inf 字面量",
                "nan" not in raw.lower() and "inf" not in raw.lower(), raw[:120])
        obj = json.loads(raw)
        r.check("alt 被清为 0", obj["alt"] == 0.0, str(obj["alt"]))
        r.check("带 dirty 标记", obj.get("dirty") is True, str(obj.get("dirty")))

    # --- T-EXPORT-005 恢复正常 ---
    print()
    print("T-EXPORT-005 恢复正常后 dirty 消失")
    reset(lua)
    g.set_state("nan_alt", False)
    g.set_state("t", t + 2.0)
    g.LuaExportAfterNextFrame()
    frames = sent(lua)
    if frames:
        obj = json.loads(frames[0]["payload"])
        r.check("不再带 dirty", obj.get("dirty") is None, str(obj.get("dirty")))
        r.check("alt 恢复", abs(obj["alt"] - 1520.25) < 0.01, str(obj["alt"]))
    else:
        r.check("能恢复发送", False)

    # --- T-EXPORT-006 停发 ---
    print()
    print("T-EXPORT-006 LuaExportStop 后不再发送")
    g.LuaExportStop()
    reset(lua)
    g.set_state("t", t + 3.0)
    g.LuaExportAfterNextFrame()
    r.check("停止后 0 帧", len(sent(lua)) == 0, f"实际 {len(sent(lua))}")

    # --- T-EXPORT-007 无 socket 时不崩 ---
    print()
    print("T-EXPORT-007 LuaSocket 缺失时优雅降级，不抛异常")
    lua2 = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua2.execute(LUA_PRELUDE.replace(
        'if name == "socket" then return fake_socket end',
        'if name == "socket" then error("not found") end'
    ))
    lua2.execute(EXPORT_LUA.read_text(encoding="utf-8"))
    try:
        lua2.globals().LuaExportStart()
        lua2.globals().LuaExportAfterNextFrame()
        r.check("没有 socket 也不崩溃", True)
        logs = lua2.globals().LOGS
        msgs = [logs[i]["msg"] for i in range(1, len(logs) + 1)] if logs else []
        r.check("记录了明确的错误日志",
                any("LuaSocket" in m for m in msgs), str(msgs[:2]))
    except Exception as e:
        r.check("没有 socket 也不崩溃", False, repr(e))

    # --- 汇总 ---
    print()
    print("=" * 60)
    total = r.passed + r.failed
    if r.failed == 0:
        print(f"  全部通过：{r.passed}/{total}")
    else:
        print(f"  通过 {r.passed}/{total}，失败 {r.failed}：")
        for f in r.failures:
            print(f"    - {f}")
    print("=" * 60)
    print()
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

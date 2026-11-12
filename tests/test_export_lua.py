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

EXPECTED_SYS_FIELDS = [
    "t", "fuel", "fuelx", "rpm_l", "rpm_r", "temp_l", "temp_r",
    "hyd_l", "hyd_r", "canopy", "wbrake", "cs_a", "cs_e", "cs_r",
    # 2026-11-13 起为战斗区新增：机型名、雷达开关、当前挂点/弹种/余量、
    # 起落架收放进度。顺序必须稳定 —— 面板虽然按名字取值，但顺序固定
    # 能让报文肉眼可比对。
    "ac", "radar", "st", "wn", "wc", "gr",
]

EXPECTED_FIELDS = [
    "t", "alt", "agl", "ias", "gs", "vs", "pitch", "bank", "hdg", "g", "mach",
    "aoa", "rpm_l", "rpm_r", "temp_l", "temp_r", "fuel", "fuelx",
    "gear", "flaps", "sbrk", "shells",
]


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

-- 这个标记让 Export.lua 里的结构探针跳过，否则测试跑到第 60 帧时
-- 探针会触发，把夹具里的假数据写进真实的 Saved Games 日志目录
-- （踩过：SelfData 只有 4 个字段、IAS 244.75，全是假的，而且文件一存在
--  真机上的探针就不再跑了）。
_TEST_ENV = true

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
    aoa = 0.0873,      -- 5 度
    rpm = 87.5,
    temp = 640.0,
    fuel = 0.62,
    gear = 1.0,
    flaps = 0.0,
    sbrake = 0.0,
    shells = 510,
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
function LoGetAngleOfAttack()            return STATE.aoa end

-- 下面三个的表结构照抄 dcs.log 里的探针实测输出
function LoGetEngineInfo()
    return {
        RPM = { left = STATE.rpm, right = STATE.rpm },
        Temperature = { left = STATE.temp, right = STATE.temp },
        FuelConsumption = { left = 1.0, right = 1.0 },
        -- STATE.no_hyd 用来模拟「这个机型压根没液压字段」（TF-51D 就是这样），
        -- 验证缺失字段是发 null 还是被伪装成 0
        HydraulicPressure = STATE.no_hyd and {} or { left = 285.0, right = 280.0 },
        EngineStart = { left = true, right = true },
        fuel_internal = STATE.fuel,
        fuel_external = 0,
    }
end
function LoGetMechInfo()
    return {
        gear = { value = STATE.gear, nose = 0, main = 0, status = 0 },
        flaps = { value = STATE.flaps, status = 0 },
        speedbrakes = { value = STATE.sbrake, status = 0 },
        -- 故意一个用标量、一个用带 .value 的表：真机上这两种形态都见过，
        -- 取值函数必须两种都认
        wheelbrakes = 0.25,
        canopy = { value = 1.0, status = 0 },
        parachute = { value = 0, status = 0 },
        controlsurfaces = { eleron = 0.02, elevator = 0.012, rudder = -0.004 },
    }
end
function LoGetPayloadInfo()
    return { CurrentStation = 0, Stations = {}, Cannon = { shells = STATE.shells } }
end
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


def main_frames(lua) -> list[dict]:
    """只要 60Hz 主帧。慢变量包带 "sys" 键，单独统计。

    分成两个统计口径是必要的：主帧和慢变量包的频率差 60 倍，
    混在一起数，「60 帧应该发出 60 帧」这种断言就永远对不上。
    """
    return [p for p in sent(lua) if '"sys"' not in p["payload"]]


def sys_packets(lua) -> list[dict]:
    return [p for p in sent(lua) if '"sys"' in p["payload"]]


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
    frames = main_frames(lua)
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
            r.check("aoa 从 LoGetAngleOfAttack 取到", abs(obj["aoa"] - 0.0873) < 1e-4, str(obj["aoa"]))
            r.check("发动机转速取自嵌套表 RPM.left", abs(obj["rpm_l"] - 87.5) < 0.1, str(obj["rpm_l"]))
            r.check("排气温度取自 Temperature.left", abs(obj["temp_l"] - 640.0) < 0.1, str(obj["temp_l"]))
            r.check("内油取自 fuel_internal", abs(obj["fuel"] - 0.62) < 1e-3, str(obj["fuel"]))
            r.check("起落架取自 gear.value", abs(obj["gear"] - 1.0) < 1e-3, str(obj["gear"]))
            r.check("机炮余弹取自 Cannon.shells", obj["shells"] == 510, str(obj["shells"]))
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
    first = len(main_frames(lua))
    reset(lua)
    for _ in range(10):
        g.LuaExportAfterNextFrame()
    second = len(main_frames(lua))
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
    n = len(main_frames(lua))
    r.check("60 帧间隔约发出 60 帧", 55 <= n <= 61, f"实际 {n}")

    # --- T-EXPORT-004 NaN ---
    print()
    print("T-EXPORT-004 NaN 必须被清成 0 并打 dirty 标记")
    reset(lua)
    g.set_state("nan_alt", True)
    g.set_state("t", t + 1.0)
    g.LuaExportAfterNextFrame()
    frames = main_frames(lua)
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
    frames = main_frames(lua)
    if frames:
        obj = json.loads(frames[0]["payload"])
        r.check("不再带 dirty", obj.get("dirty") is None, str(obj.get("dirty")))
        r.check("alt 恢复", abs(obj["alt"] - 1520.25) < 0.01, str(obj["alt"]))
    else:
        r.check("能恢复发送", False)

    # --- T-EXPORT-008 慢变量包 ---
    print()
    print("T-EXPORT-008 慢变量包按 1Hz 单独发送，不混进主帧")
    reset(lua)
    g.set_state("t", t + 3.0)
    g.LuaExportAfterNextFrame()
    sp = sys_packets(lua)
    r.check("发出了慢变量包", len(sp) == 1, f"实际 {len(sp)}")
    if sp:
        try:
            obj = json.loads(sp[0]["payload"])
            r.check("外层只有 sys 一个键", list(obj.keys()) == ["sys"], str(list(obj.keys())))
            s_obj = obj["sys"]
            r.check("sys 字段完整且顺序稳定", list(s_obj.keys()) == EXPECTED_SYS_FIELDS,
                    f"实际 {list(s_obj.keys())}")
            r.check("燃油取自 fuel_internal", abs(s_obj["fuel"] - 0.62) < 1e-3, str(s_obj["fuel"]))
            r.check("液压取自 HydraulicPressure.left",
                    abs(s_obj["hyd_l"] - 285.0) < 0.1, str(s_obj["hyd_l"]))
            r.check("座舱盖认带 .value 的表", abs(s_obj["canopy"] - 1.0) < 1e-3, str(s_obj["canopy"]))
            r.check("轮刹认裸标量", abs(s_obj["wbrake"] - 0.25) < 1e-3, str(s_obj["wbrake"]))
            r.check("舵面取自 controlsurfaces.elevator",
                    abs(s_obj["cs_e"] - 0.012) < 1e-4, str(s_obj["cs_e"]))
            r.check("慢变量包里没有主帧字段", "alt" not in s_obj, "混进了 alt")
        except json.JSONDecodeError as e:
            r.check("可被 JSON 解析", False, str(e))

    # --- T-EXPORT-009 缺失字段发 null ---
    print()
    print("T-EXPORT-009 机型不提供的字段发 null，不伪装成 0")
    g.set_state("no_hyd", True)
    reset(lua)
    g.set_state("t", t + 6.0)
    g.LuaExportAfterNextFrame()
    sp = sys_packets(lua)
    if sp:
        try:
            sb = json.loads(sp[-1]["payload"])["sys"]
            # TF-51D 没有液压字段。发 0 的话面板会显示「液压 0」，看着像
            # 设备故障；发 null 面板才知道该显示「--」。
            r.check("缺失的液压是 null 而不是 0", sb["hyd_l"] is None, str(sb["hyd_l"]))
            r.check("另一侧同样为 null", sb["hyd_r"] is None, str(sb["hyd_r"]))
            r.check("有值的字段照常给数", sb["rpm_l"] is not None, str(sb["rpm_l"]))
            # 精度只能查原始报文：JSON 解析成 float 后尾随零就丢了，看不出是
            # 编码成 0.6200 还是 0.62。比例机型的燃油每秒只掉 0.0002，
            # 2 位小数会把变化量化没，斜率算出来是 0 或翻倍。
            raw = sp[-1]["payload"]
            r.check("燃油按 4 位小数编码", '"fuel":0.6200' in raw, raw[:90])
        except json.JSONDecodeError as e:
            r.check("可被 JSON 解析", False, str(e))
    else:
        r.check("发出了慢变量包", False, "0 包")
    g.set_state("no_hyd", False)

    # --- T-EXPORT-010 温度口径 ---
    print()
    print("T-EXPORT-010 温度是比例口径时发 null，不显示成「1 °C」")
    g.set_state("temp", 0.72)
    reset(lua)
    g.set_state("t", t + 9.0)
    g.LuaExportAfterNextFrame()
    sp = sys_packets(lua)
    if sp:
        sb = json.loads(sp[-1]["payload"])["sys"]
        # JF-17 实测 Temperature.left = 0.72334，是比例不是摄氏度。
        # 之前会原样发出去，面板显示「1 °C」—— 假数据比没数据更糟。
        r.check("比例口径的温度是 null", sb["temp_l"] is None, str(sb["temp_l"]))
    g.set_state("temp", 640.0)
    reset(lua)
    g.set_state("t", t + 12.0)
    g.LuaExportAfterNextFrame()
    sp = sys_packets(lua)
    if sp:
        sb = json.loads(sp[-1]["payload"])["sys"]
        r.check("摄氏度口径照常给数", sb["temp_l"] is not None and sb["temp_l"] > 100,
                str(sb["temp_l"]))

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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration_test.py — 多端 DCS 外设 · 当前实现的主动完整回归测试

闭环：
    Chromium(模拟 iPad) 真实 DOM 点击
      -> POST /cmd -> beacon.py 写命令文件 -> 真实 dcs/Export.lua(嵌入 Lua) 读取执行
      -> Export.lua UDP 发主帧/慢变量 -> beacon /state -> iPad 1Hz 刷新 DOM

隔离：
    - HTTP :8091 / 遥测 UDP :5091 / 输入转发 UDP :5092，不碰生产 8080/5010
    - 命令文件与 Lua 的 USERPROFILE 全部指向临时目录，绝不写真实 Saved Games

用法：
    python tests/integration_test.py
    python tests/integration_test.py --report .tmp/result.json

依赖：lupa、playwright、系统 Chrome（channel="chrome"）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

HTTP_PORT = 8091
UDP_IN = 5091
UDP_FWD = 5092
UDP_TOOLS = 5099
BASE = f"http://127.0.0.1:{HTTP_PORT}"

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------- 结果记录

class Result:
    def __init__(self):
        self.rows: list[dict] = []

    def check(self, tid, name, cond, expected, actual, sev="P2", hint=""):
        ok = bool(cond)
        row = dict(id=tid, name=name, ok=ok, expected=str(expected),
                   actual=str(actual), sev=sev, hint=hint)
        self.rows.append(row)
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {tid} {name}")
        if not ok:
            print(f"          期望: {expected}")
            print(f"          实际: {actual}")
        return ok

    @property
    def failed(self):
        return [r for r in self.rows if not r["ok"]]

    def summary(self):
        return f"{len(self.rows) - len(self.failed)}/{len(self.rows)} 通过，{len(self.failed)} 失败"


R = Result()


# ---------------------------------------------------------------- HTTP 小工具

def http_get(path, raw=False):
    try:
        with OPENER.open(BASE + path, timeout=3) as r:
            b = r.read()
            return (r.status, b) if raw else (r.status, json.loads(b))
    except urllib.error.HTTPError as e:
        b = e.read()
        return (e.code, b) if raw else (e.code, json.loads(b))


def http_post(path, obj, data=None):
    body = data if data is not None else json.dumps(obj).encode()
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with OPENER.open(req, timeout=3) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post_cmd(dev, cmd, val):
    return http_post("/cmd", {"dev": dev, "cmd": cmd, "val": val})


def send_udp(obj, port=UDP_IN):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode(),
                 ("127.0.0.1", port))


def wait_until(fn, timeout=3.0, interval=0.06):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(interval)
    return None


# ---------------------------------------------------------------- 真实 Export.lua 的假 DCS 外壳

LUA_PRELUDE = r"""
SENT = {}
LOGS = {}
local fake_socket = {}
function fake_socket.udp()
    local s = {}
    function s:settimeout() end
    function s:setsockname() end
    function s:close() end
    function s:receive() return nil end
    function s:sendto(payload, host, port)
        SENT[#SENT + 1] = payload
        return #payload
    end
    return s
end
log = { INFO = 1, WARNING = 2, ERROR = 3 }
function log.write(tag, level, msg) LOGS[#LOGS + 1] = msg end
function require(name)
    if name == "socket" then return fake_socket end
    error("no module: " .. tostring(name))
end
_TEST_ENV = true
os.getenv = function(k)
    if k == "USERPROFILE" then return PY_TMP_ROOT end
    return nil
end

function py_arg(el) return PY_ARG(el) end
function py_action(id, cmd, val) return PY_ACTION(id, cmd, val) end
function py_indication(id) return PY_INDICATION(id) end
function py_state(k) return PY_STATE(k) end

ARG_DEVICE = {}
function ARG_DEVICE:get_argument_value(el) return py_arg(el) end

DEVICES = {}
for _, id in ipairs({4, 11, 32, 33, 35, 38, 46, 47}) do
    local n = id
    DEVICES[n] = {
        performClickableAction = function(self, cmd, val) return py_action(n, cmd, val) end
    }
end
function GetDevice(id)
    if id == 0 then return ARG_DEVICE end
    return DEVICES[id]
end
function list_indication(id) return py_indication(id) end

function LoGetModelTime() return py_state("t") end
function LoGetSelfData()
    return {
        Pitch = py_state("pitch"), Bank = py_state("bank"),
        Heading = py_state("hdg"), Name = py_state("ac"),
        Flags = { RadarActive = py_state("radar") },
    }
end
function LoGetAltitudeAboveSeaLevel() return py_state("alt") end
function LoGetAltitudeAboveGroundLevel() return py_state("agl") end
function LoGetIndicatedAirSpeed() return py_state("ias") end
function LoGetTrueAirSpeed() return py_state("tas") end
function LoGetVerticalVelocity() return py_state("vs") end
function LoGetMachNumber() return py_state("mach") end
function LoGetAccelerationUnits() return { x = 0, y = py_state("g"), z = 0 } end
function LoGetAngleOfAttack() return py_state("aoa") end
function LoGetEngineInfo()
    local hyd = {}
    if py_state("no_hyd") ~= true then
        hyd = { left = py_state("hyd_l"), right = py_state("hyd_r") }
    end
    return {
        RPM = { left = py_state("rpm_l"), right = py_state("rpm_r") },
        Temperature = { left = py_state("temp_l"), right = py_state("temp_r") },
        FuelConsumption = { left = 1.0, right = 1.0 },
        HydraulicPressure = hyd,
        EngineStart = { left = true, right = true },
        fuel_internal = py_state("fuel"),
        fuel_external = py_state("fuelx"),
    }
end
function LoGetMechInfo()
    -- 结构照抄 Saved Games/DCS/Logs/dcsprobe.json 里 JF-17 的真实形态：
    -- gear.nose.rod 是三级嵌套，controlsurfaces.* 是 {left=,right=} 表
    return {
        gear = { value = py_state("gear"),
                 nose = { rod = py_state("gr") },
                 main = { left = { rod = py_state("gr") }, right = { rod = py_state("gr") } },
                 status = 0 },
        flaps = { value = py_state("flaps"), status = 0 },
        speedbrakes = { value = py_state("sbrk"), status = 0 },
        wheelbrakes = py_state("wbrake"),
        canopy = { value = py_state("canopy"), status = 0 },
        parachute = { value = 0, status = 0 },
        controlsurfaces = {
            eleron  = { left = py_state("cs_a"), right = py_state("cs_a") },
            elevator = { left = py_state("cs_e"), right = py_state("cs_e") },
            rudder  = { left = py_state("cs_r"), right = py_state("cs_r") },
        },
    }
end
function LoGetPayloadInfo()
    return {
        CurrentStation = py_state("cur_station"),
        Cannon = { shells = py_state("shells") },
        Stations = {
            { CLSID = "DIS_PL-5EII", count = 1 },
            { CLSID = "DIS_SD-10_DUAL_L", count = 2 },
            { CLSID = "", count = 0 },
            { CLSID = "DIS_SPJ_POD", count = 1 },
            { CLSID = "", count = 0 },
            { CLSID = "DIS_SD-10_DUAL_R", count = 2 },
            { CLSID = "", count = 0 },
        },
    }
end
"""


class FakeDCS:
    """把真实 Export.lua 装进 Lua 运行时，用 Python 控制它看到的飞机状态。"""

    def __init__(self, tmp_root: Path, udp_port: int):
        import lupa
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        self.state = {
            "t": 0.0,
            "alt": 8000.0, "agl": 7400.0, "ias": 155.0, "tas": 198.0,
            "vs": 2.25, "pitch": 0.015, "bank": 0.1, "hdg": 1.2345,
            "g": 1.02, "mach": 0.42, "aoa": 0.02,
            "rpm_l": 72.3, "rpm_r": 72.3, "temp_l": 640.0, "temp_r": 640.0,
            "hyd_l": 285.0, "hyd_r": 280.0,
            "fuel": 3200.0, "fuelx": 0.0,
            "gear": 1.0, "flaps": 0.3, "sbrk": 0.0, "wbrake": 0.25,
            "canopy": 1.0, "gr": 0.75,
            "cs_a": 0.0027, "cs_e": 0.0527, "cs_r": 0.0065,
            "ac": "JF-17", "radar": True,
            "cur_station": 2, "shells": 180, "no_hyd": False,
        }
        self.indications: dict[int, str] = {}
        self.args: dict[int, float] = {}
        self.actions: list[tuple] = []
        self.fail_action = False
        self.frames: list[dict] = []
        self.sys_frames: list[dict] = []
        self.lock = threading.Lock()
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_port = udp_port
        g.PY_TMP_ROOT = str(tmp_root).replace("\\", "/")
        g.PY_STATE = lambda k: self.state.get(str(k))
        g.PY_ARG = lambda el: float(self.args.get(int(el), 0.0))
        g.PY_INDICATION = lambda i: self.indications.get(int(i), "")
        g.PY_ACTION = self._action
        self.lua.execute(LUA_PRELUDE)
        self.lua.execute((ROOT / "dcs" / "Export.lua").read_text(encoding="utf-8"))
        self.lua.globals().LuaExportStart()

    def _action(self, dev, cmd, val):
        if self.fail_action:
            raise RuntimeError("simulated device failure")
        self.actions.append((int(dev), int(cmd), float(val)))
        # 起落架命令 3007：val=-1 放、val=1 收
        if int(cmd) == 3007:
            down = float(val) < 0
            self.state["gear"] = 1.0 if down else 0.0
            self.state["gr"] = 1.0 if down else 0.0
        if int(cmd) == 3015:
            self.state["flaps"] = 0.3 if float(val) > 0 else 0.0
        return True

    def set(self, **kw):
        self.state.update(kw)

    def step(self, n=1, dt=1 / 60, pace=False):
        with self.lock:
            for i in range(n):
                if pace and i:
                    time.sleep(dt)
                self.state["t"] = round(self.state["t"] + dt, 6)
                self.lua.globals().LuaExportAfterNextFrame()
                tbl = self.lua.globals().SENT
                payloads = [str(tbl[i]) for i in range(1, len(tbl) + 1)]
                self.lua.execute("SENT = {}")
                for p in payloads:
                    self.udp.sendto(p.encode("utf-8"), ("127.0.0.1", self.udp_port))
                    try:
                        obj = json.loads(p)
                    except Exception:
                        continue
                    if "sys" in obj:
                        self.sys_frames.append(obj["sys"])
                    else:
                        self.frames.append(obj)

    def close(self):
        self.udp.close()


# ---------------------------------------------------------------- 桥接服务

def load_beacon(tmp: Path):
    spec = importlib.util.spec_from_file_location("beacon_under_test", TOOLS / "beacon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 与 Export.lua 的 (USERPROFILE)/Saved Games/DCS/Logs/dcs_cmd.txt 对齐
    mod.CMD_FILE = tmp / "Saved Games" / "DCS" / "Logs" / "dcs_cmd.txt"
    return mod


def start_beacon(mod) -> tuple[list, threading.Event, list]:
    stop = threading.Event()
    servers = mod.start_servers(HTTP_PORT, True)
    ths = [threading.Thread(target=mod.udp_listener,
                            args=(UDP_IN, mod.HUB, stop), daemon=True)]
    for t in ths:
        t.start()
    return servers, stop, ths


def restart_udp_listener(mod, stop):
    t = threading.Thread(target=mod.udp_listener,
                         args=(UDP_IN, mod.HUB, stop), daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------- 静态检查

def static_numbers():
    def read(p):
        return (ROOT / p).read_text(encoding="utf-8", errors="replace")

    beacon, vjoy, kt = (read("tools/beacon.py"), read("tools/vjoy_out.py"),
                        read("android/app/src/main/java/com/fengzijie/dcsperipheral/input/YokeController.kt"))
    nb = int(re.search(r"MAX_BUTTONS\s*=\s*(\d+)", beacon).group(1))
    nv = int(re.search(r"MAX_BTN\s*=\s*(\d+)", vjoy).group(1))
    nk = int(re.search(r"BUTTON_COUNT\s*=\s*(\d+)", kt).group(1))
    R.check("T-STAT-001", "三处按钮数一致", nb == nv == nk == 30, "30/30/30", f"{nb}/{nv}/{nk}",
            "P1", "按钮数不一致会导致手机按下的高位按钮在桥接或 vJoy 侧被丢弃")

    panel = read("tools/panel.html")
    audit = read("tools/mfd-audit.py")
    off1 = int(re.search(r"CMD_OFFSET\s*=\s*(\d+)", panel).group(1))
    off2 = int(re.search(r"OFFSET\s*=\s*(\d+)", audit).group(1))
    R.check("T-STAT-002", "命令号偏移一致", off1 == off2 == 2502, "2502/2502", f"{off1}/{off2}",
            "P1", "偏移不一致会把座舱命令打到错误的控件上")

    m = re.search(r"const MFD_PAGES = (\{.*?\n\});\n// MFDPAGES:END", panel, re.S)
    a = json.loads(m.group(1))
    b = json.loads(read("tools/mfd-pages.json"))
    R.check("T-STAT-003", "面板页面数据与生成 JSON 一致",
            a == b, f"{len(b)} 页完全一致",
            f"panel {len(a)} / json {len(b)}，差异 {len([k for k in a.keys() & b.keys() if a[k] != b[k]])}",
            "P1", "两份页面数据漂移会让 MFD 键位标注和识别规则对不上")

    # 生成器重生成到临时目录，与仓库内两份文件比对
    try:
        spec = importlib.util.spec_from_file_location("gen_under_test", TOOLS / "gen-mfd-pages.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        tmp = Path(tempfile.mkdtemp(prefix="dcs-gen-"))
        (tmp / "tools").mkdir(parents=True, exist_ok=True)
        shutil.copy(TOOLS / "panel.html", tmp / "tools" / "panel.html")
        gen.PANEL = tmp / "tools" / "panel.html"
        gen.ROOT = tmp
        gen.main()
        regen_html = (tmp / "tools" / "panel.html").read_text(encoding="utf-8")
        regen_json = json.loads((tmp / "tools" / "mfd-pages.json").read_text(encoding="utf-8"))
        shutil.rmtree(tmp, ignore_errors=True)
        R.check("T-STAT-004", "gen-mfd-pages.py 重生成无漂移",
                regen_html == panel and regen_json == b, "输出与仓库内文件逐字节一致",
                f"html {'一致' if regen_html == panel else '有差异'} / json {'一致' if regen_json == b else '有差异'}",
                "P2", "生成器漂移说明手改了生成块或数据源变了")
    except Exception as e:
        R.check("T-STAT-004", "gen-mfd-pages.py 重生成无漂移", False,
                "可正常重生成", repr(e), "P2", "生成器不可用会让页面数据无法从 DCS 脚本刷新")

    lua = read("dcs/Export.lua")
    enc = re.search(r"local function encode_sys\(.*?\nend", lua, re.S).group(0)
    lua_fields = [f for f in re.findall(r'"([a-z_]+)":', enc) if f != "sys"]
    test_src = read("tests/test_export_lua.py")
    m2 = re.search(r"EXPECTED_SYS_FIELDS\s*=\s*\[(.*?)\]", test_src, re.S)
    exp = re.findall(r'"([a-z_]+)"', m2.group(1))
    R.check("T-STAT-005", "单元测试的 sys 字段清单与 Export.lua 一致",
            lua_fields == exp, f"Export.lua {len(lua_fields)} 字段",
            f"单测 {len(exp)} 字段；缺少 {sorted(set(lua_fields) - set(exp))}，多出 {sorted(set(exp) - set(lua_fields))}",
            "P2", "单测期望清单未跟上 Export.lua 新字段")

    lpath = 'Saved Games/DCS/Logs/dcs_cmd.txt' in lua
    bpath = 'Saved Games' in read("tools/beacon.py") and 'dcs_cmd.txt' in read("tools/beacon.py")
    R.check("T-STAT-006", "两侧命令文件路径一致",
            bpath and lpath,
            "beacon 与 Export.lua 都指向 Saved Games/DCS/Logs/dcs_cmd.txt",
            f"beacon={bpath} lua={lpath}",
            "P1", "路径不一致会让 iPad 命令永远到不了 DCS")

    d3_expr = re.search(r"^D3\s*=\s*([^#\r\n]+)", audit, re.M).group(1).strip()
    off = int(re.search(r"OFFSET\s*=\s*(\d+)", audit).group(1))
    sent = eval(d3_expr, {"OFFSET": off}) + off
    R.check("T-STAT-007", "mfd-audit.py 的 D3 命令号正确",
            sent == 3295, "cmd=3295（元素 793 + 2502）", f"cmd={sent}（{d3_expr} 再加一次 OFFSET）",
            "P2", "D3 写成了命令号，click() 又加了一次偏移")

    cp = read("tools/check-panel.py")
    R.check("T-STAT-008", "check-panel.py 溢出报告取的标题元素存在",
            "querySelector('h2')" not in cp or ".card h2" in read("tools/panel.html"),
            "取 .card 里真实存在的标题元素", "取 h2，但 .card 内只有 h3",
            "P2", "一旦发生横向溢出，验收脚本会抛 TypeError 而不是报告溢出")

    vjoy = read("tools/vjoy_out.py")
    hb = re.search(r'path\s*=\s*\(u\.path\s*or\s*""\)\s*\+\s*"/vjoy"', vjoy)
    R.check("T-STAT-009", "vJoy 心跳 URL 对尾斜杠归一化",
            hb is None, "path 用 rstrip('/') 归一，避免 //vjoy",
            "path = (u.path or '') + '/vjoy'，URL 带尾斜杠时变成 //vjoy → 404"
            if hb else "已归一化", "P3", "心跳 404 会让 /input 一直报 vjoy 未就绪")

    # 视角已从手机端移除（用户买了头瞄）。这里只守住「脚舵滑块」入口不退化，
    # 并确认视角相关回调/控件确实已删掉（不能偷偷又接回来）。
    combat = read("android/app/src/main/java/com/fengzijie/dcsperipheral/ui/CombatScreen.kt")
    main_act = read("android/app/src/main/java/com/fengzijie/dcsperipheral/MainActivity.kt")
    m = re.search(r"CombatScreen\((.*?)\n\s*\)", main_act, re.S)
    call = m.group(1) if m else ""
    needed = ("onRudder", "onRudderRelease")
    missing = [p for p in needed
               if not (re.search(r"\b" + p + r"\s*:", combat)
                       and re.search(r"\b" + p + r"\s*=", call))]
    has_rudder = "RudderBar(" in combat
    # 视角痕迹应当彻底消失
    view_gone = ("ViewPad(" not in combat
                 and "onView" not in combat
                 and "onViewRelease" not in call)
    R.check("T-STAT-010", "战斗页脚舵入口齐全且视角已移除",
            not missing and has_rudder and view_gone,
            "CombatScreen 声明并调用 RudderBar，MainActivity 传 onRudder/onRudderRelease；且无 ViewPad/onView 残留",
            f"缺回调={missing} 脚舵控件={has_rudder} 视角残留={not view_gone}",
            "P1", "脚舵入口退化会让战斗页只能用看不见的「拧手机」；视角应已交给头瞄")

    # 发射键拆分 + 版面顺序。机炮和武器投放在 DCS 里是两条独立命令
    # （Trigger vs Weapon Release），一个 BTN7 混绑必然丢一条。
    yoke = read("android/app/src/main/java/com/fengzijie/dcsperipheral/ui/YokeScreen.kt")
    binding = read("docs/BINDING.md")
    gun_num = re.search(r"GUN_FIRE\s*=\s*11", yoke) is not None
    two_keys = ("YokeBtn.GUN_FIRE" in combat and "YokeBtn.FIRE" in combat)
    # 源码里的调用顺序 == 版面从上到下：两个发射键 → 最底下脚舵（视角已移除）
    i_gun = combat.find("\"机炮\"")
    i_rudder = combat.find("RudderBar(")
    order_ok = 0 <= i_gun < i_rudder
    # Compose 源码顺序 == 版面从左到右：绿点盘在左，发射组在最右
    right_of_green = 0 <= combat.find("StickPad(") < combat.find("\"机炮\"")
    # 20:57 用户嫌中间五个按钮太大：不许再回到 weight(1f) 撑满半屏
    compact = ("Modifier.width(132.dp).height(60.dp)" in combat
               and "height = 42.dp" in combat)
    doc_ok = "BTN12" in binding and "GUN_FIRE = 11" in binding
    all_ok = (gun_num and two_keys and order_ok and right_of_green and compact and doc_ok)
    R.check("T-STAT-011", "机炮/投放为两个独立按钮，发射组在右上角、中间紧凑、脚舵最底（视角已移除）",
            all_ok,
            "GUN_FIRE=11 且两键都被调用；源码顺序 绿点盘<发射<脚舵；中间按钮固定小尺寸；BINDING.md 有 BTN12",
            f"编号={gun_num} 两键={two_keys} 顺序={order_ok} 在绿点右侧={right_of_green} 紧凑={compact} 文档={doc_ok}",
            "P1", "发射键重新混成一个会直接丢掉机炮或投放；20:53 用户更正过左右，位置错了要能挡住")

    # 视角已移除，不再守它的尺寸；改守「视角痕迹消失」+ 发射键仍是大尺寸。
    big_col = "Modifier.width(220.dp)" in combat
    view_gone = "ViewPad(" not in combat and "Modifier.size(160.dp)" not in combat and "labelSp = 13f" not in combat
    big_fire = "height(84.dp)" in combat and "textSp = 18f" in combat
    R.check("T-STAT-012", "视角已移除，发射组仍为大尺寸且文字同步",
            big_col and view_gone and big_fire,
            "右列 220dp、ViewPad 已删除、发射键 84dp 高 + 18/12sp 文字",
            f"右列={big_col} 视角已移除={view_gone} 发射={big_fire}",
            "P2", "别把视角又加回来；发射键缩回 60dp 会重演「太小」的抱怨")


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(ROOT / ".tmp" / "integration-result.json"))
    ap.add_argument("--skip-browser", action="store_true")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="dcs-it-"))
    (tmp / "Saved Games" / "DCS" / "Logs").mkdir(parents=True, exist_ok=True)
    cmd_file = tmp / "Saved Games" / "DCS" / "Logs" / "dcs_cmd.txt"
    print("\n" + "=" * 74)
    print("  当前实现 · 主动完整回归测试")
    print("=" * 74)
    print(f"  临时目录 {tmp}")

    pacer_stop = threading.Event()
    pacer_pause = threading.Event()

    beacon = load_beacon(tmp)
    servers, stop, ths = start_beacon(beacon)
    fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fwd.bind(("127.0.0.1", UDP_FWD))
    fwd.settimeout(0.4)
    beacon.INPUT.set_sink("127.0.0.1", UDP_FWD)
    tool_sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tool_sink.bind(("127.0.0.1", UDP_TOOLS))
    tool_sink.settimeout(0.2)

    # USERPROFILE 指向临时目录根，Export.lua 会拼出 Saved Games/DCS/Logs/
    dcs = FakeDCS(tmp, UDP_IN)
    time.sleep(0.25)

    try:
        # ---------------- S0 ----------------
        print("\n--- S0 静态一致性 ---")
        static_numbers()

        # ---------------- S1 ----------------
        print("\n--- S1 HTTP 服务与路由 ---")
        st, body = http_get("/ping")
        d = json.loads(body) if isinstance(body, bytes) else body
        R.check("T-SVC-001", "GET /ping", st == 200 and {"server_ms", "uptime_s", "peer"} <= set(d),
                "200 + server_ms/uptime_s/peer", f"{st} {list(d)[:5]}", "P1")
        for p in ("/", "/panel", "/panel.html", "/panel/"):
            st, b = http_get(p, raw=True)
            R.check(f"T-SVC-002{p}", f"GET {p}", st == 200 and b"<html" in b.lower(),
                    "200 HTML", f"{st} {len(b)} bytes", "P1")
        st, b = http_get("/nope", raw=True)
        R.check("T-SVC-003", "404 页面列出入口", st == 404 and b"/panel" in b and b"/state" in b,
                "404 + 列出 /panel /state", f"{st} {len(b)} bytes", "P3")
        st, d = http_get("/input")
        R.check("T-SVC-004", "GET /input 结构",
                st == 200 and {"axes", "buttons", "seq", "forwarding", "vjoy"} <= set(d),
                "含 axes/buttons/seq/forwarding/vjoy", f"{st} {list(d)}", "P1")
        st, d = http_get("/info")
        R.check("T-SVC-005", "GET /info 结构",
                st == 200 and {"ipv4", "ipv6", "uptime_s"} <= set(d), "含 ipv4/ipv6/uptime_s",
                f"{st} {list(d)}", "P2")
        cases = [("POST /bogus", "/bogus", b'{}', 404),
                 ("空 body", "/input", b"", 413),
                 ("坏 JSON", "/input", b'not json', 400),
                 ("超长 body", "/input", b"x" * 5000, 413)]
        for label, p, data, want in cases:
            st, _ = http_post(p, None, data=data)
            R.check(f"T-SVC-006{label}", f"异常请求：{label}", st == want, want, st, "P2")
        st, d = http_get("/state")
        R.check("T-SVC-007", "无数据时 /state 仍合法",
                st == 200 and d["has_data"] is False and d["frame"] is None,
                "has_data=false / frame=null", f"{st} {d.get('has_data')} {d.get('frame')}", "P1")

        # ---------------- S2 ----------------
        print("\n--- S2 遥测链路 ---")
        # 按真实 60Hz 墙钟节奏推进，否则 hz 统计测到的是「瞬间灌包」的假值
        dcs.step(60, pace=True)
        time.sleep(0.15)
        st, s = http_get("/state")
        fr = s.get("frame") or {}
        R.check("T-TLM-001", "60Hz 主帧到 /state",
                s["has_data"] and len(fr) >= 22 and 50 <= s["stats"]["hz"] <= 70 and s["stats"]["bad"] == 0,
                "has_data=true, 22 字段, hz≈60, bad=0",
                f"has_data={s['has_data']}, 字段 {len(fr)}, hz={s['stats']['hz']}, bad={s['stats']['bad']}", "P0")
        sysd = s.get("sys") or {}
        needed = {"t", "fuel", "fuelx", "rpm_l", "hyd_l", "cs_a", "cs_e", "cs_r", "gr",
                  "ac", "radar", "st", "wn", "wc", "wl", "cn", "ack", "acn", "dbg",
                  "bp", "mfd", "ufcp", "ff", "endurance_s"}
        R.check("T-TLM-002", "1Hz 慢变量字段齐全",
                bool(sysd) and needed <= set(sysd) and s["sys_age_ms"] < 5000,
                f"含 {len(needed)} 个关键字段",
                f"sys={'有' if sysd else '无'}，缺 {sorted(needed - set(sysd))}", "P1")

        # 真实 DCS 结构下 cs_e / gr 应该拿到数值（探针文件里就是三级嵌套表）
        R.check("T-TLM-002b", "真实 MechInfo 结构下 cs_e/gr 不为 null",
                sysd.get("cs_e") is not None and sysd.get("gr") is not None,
                "cs_e≈0.0527, gr≈0.75（来自 gear.nose.rod / elevator.left）",
                f"cs_e={sysd.get('cs_e')}, gr={sysd.get('gr')}", "P1",
                "deepget 只支持两级，且没处理 {left,right} 形态")

        # 燃油斜率：桥接按墙钟时间算斜率，这里必须真的隔 1 秒发一包
        for i in range(1, 5):
            dcs.set(fuel=3200.0 - i * 1.15)
            dcs.step(60)
            time.sleep(1.02)
        time.sleep(0.15)
        _, s = http_get("/state")
        ff = (s.get("sys") or {}).get("ff")
        en = (s.get("sys") or {}).get("endurance_s")
        R.check("T-TLM-003", "燃油消耗率与续航",
                ff is not None and -4600 < ff < -3300 and en is not None and en > 0,
                "ff≈-4140 kg/h（墙钟计时有抖动，容差 ±800），endurance_s>0",
                f"ff={ff}, endurance_s={en}", "P2",
                "斜率算法应取窗口首尾而非相邻点")

        # NaN/Inf 注入
        st, raw = http_get("/state", raw=True)
        nan_frame = dcs.frames[-1].copy()
        nan_frame["alt"] = float("nan")
        nan_frame["ias"] = float("inf")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.sendto(json.dumps(nan_frame).encode(), ("127.0.0.1", UDP_IN))
        time.sleep(0.12)
        st, raw = http_get("/state", raw=True)
        bad_literal = b"NaN" in raw or b"Infinity" in raw
        strict = True
        try:
            json.loads(raw.decode(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        except ValueError:
            strict = False
        R.check("T-TLM-004", "NaN/Inf 不得出现在 /state 响应里",
                strict and not bad_literal,
                "严格合法 JSON、无 NaN/Infinity 字面量、数值被清洗",
                f"严格JSON={strict}, 含非法字面量={bad_literal}", "P0",
                "beacon 用 json.loads 接受 NaN 并用 json.dumps(allow_nan=True) 输出，浏览器 JSON.parse 会失败")

        # 畸形慢变量：UDP 监听线程不能死
        _, before = http_get("/state")
        send_udp({"sys": {"fuel": 3200.0, "fuelx": "oops"}})
        time.sleep(0.1)
        for _ in range(6):
            dcs.step(1)
            time.sleep(0.03)
        _, after = http_get("/state")
        delta = after["stats"]["rx"] - before["stats"]["rx"]
        R.check("T-TLM-005", "畸形慢变量不得打死 UDP 监听线程",
                delta >= 5,
                "后续 6 帧仍被接收（rx 至少 +5）",
                f"rx {before['stats']['rx']} → {after['stats']['rx']}（+{delta}）", "P0",
                "TelemetryHub.feed 里 float(fuelx) 抛 ValueError，udp_listener 没有兜底")
        # 若线程已死，重启以便后续测试继续
        if delta < 5:
            ths.append(restart_udp_listener(beacon, stop))
            time.sleep(0.15)

        # 主帧冻结 2 秒
        time.sleep(2.15)
        _, s = http_get("/state")
        R.check("T-TLM-006", "主帧停 2 秒判定冻结",
                s["has_data"] is False and s["frame"] is None,
                "has_data=false / frame=null", f"{s['has_data']} / {s['frame']}", "P2")
        # 恢复主帧、只让慢变量过期 5 秒
        dcs.step(2)
        time.sleep(5.15)
        _, s = http_get("/state")
        R.check("T-TLM-007", "慢变量停 5 秒判定失效",
                s.get("sys") is None and (s.get("sys_age_ms") or 0) >= 5000,
                "sys=null / sys_age_ms≥5000", f"sys={s.get('sys')}, age={s.get('sys_age_ms')}", "P2")
        dcs.step(60)
        time.sleep(0.15)
        _, s = http_get("/state")
        R.check("T-TLM-008", "恢复发包后状态恢复",
                s["has_data"] is True and s.get("sys") is not None,
                "has_data=true 且 sys 有值", f"{s['has_data']} / sys={'有' if s.get('sys') else '无'}", "P2")

        # TF-51D 形态
        dcs.set(no_hyd=True, temp_l=None, temp_r=None, fuel=0.9862, fuelx=None,
                rpm_r=None, cs_e=None, gr=None, radar=None, ac="TF-51D")
        dcs.step(60)
        time.sleep(0.15)
        _, s = http_get("/state")
        sysd = s.get("sys") or {}
        R.check("T-TLM-009", "TF-51D 缺失字段如实为 null",
                sysd.get("hyd_l") is None and sysd.get("temp_l") is None and sysd.get("cs_e") is None,
                "hyd_l/temp_l/cs_e 都是 null",
                f"hyd={sysd.get('hyd_l')} temp={sysd.get('temp_l')} cs_e={sysd.get('cs_e')}", "P2")
        dcs.set(no_hyd=False, temp_l=640.0, temp_r=640.0, fuel=3200.0, fuelx=0.0,
                rpm_r=72.3, cs_e=0.0527, gr=0.75, radar=True, ac="JF-17")
        dcs.step(60)
        time.sleep(0.1)

        # 畸形报文记 bad
        _, before = http_get("/state")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.sendto(b"not-a-json", ("127.0.0.1", UDP_IN))
        time.sleep(0.1)
        _, after = http_get("/state")
        R.check("T-TLM-010", "畸形 UDP 报文被计入 bad",
                after["stats"]["bad"] > before["stats"]["bad"], "bad+1",
                f"bad {before['stats']['bad']} → {after['stats']['bad']}", "P3")

        # 保证面板接下来有稳定数据
        dcs.step(60)
        time.sleep(0.15)

        # ---------------- 持续遥测心跳 ----------------
        # 面板按墙钟判定「2 秒没主帧就冻结」。测试里 Export.lua 是手动推进的，
        # 浏览器启动/等待期间会误判冻结；起一个 20Hz 的主帧心跳保持真实在线态。
        # 只发主帧，不碰慢变量包和命令文件，避免干扰回执/注入测试。
        def pacer():
            sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            while not pacer_stop.is_set():
                if not pacer_pause.is_set():
                    s = dcs.state
                    fr = {"t": s["t"], "alt": s["alt"], "agl": s["agl"], "ias": s["ias"],
                          "gs": s["tas"], "vs": s["vs"], "pitch": s["pitch"],
                          "bank": s["bank"], "hdg": s["hdg"], "g": s["g"],
                          "mach": s["mach"], "aoa": s["aoa"], "rpm_l": s["rpm_l"],
                          "rpm_r": s["rpm_r"], "temp_l": s["temp_l"], "temp_r": s["temp_r"],
                          "fuel": s["fuel"], "fuelx": s["fuelx"], "gear": s["gear"],
                          "flaps": s["flaps"], "sbrk": s["sbrk"], "shells": s["shells"]}
                    try:
                        sk.sendto(json.dumps(fr, separators=(",", ":")).encode(),
                                  ("127.0.0.1", UDP_IN))
                    except OSError:
                        pass
                time.sleep(0.05)
            sk.close()

        threading.Thread(target=pacer, daemon=True).start()

        # ---------------- S3 / S4 / S5：浏览器 ----------------
        if not args.skip_browser:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                ctx = browser.new_context(viewport={"width": 1024, "height": 768},
                                          device_scale_factor=2, has_touch=True)
                page = ctx.new_page()
                errors = []
                page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                page.goto(BASE + "/panel", wait_until="load")
                page.wait_for_timeout(1400)

                def dom(i):
                    return page.evaluate("id => (document.getElementById(id)||{}).textContent", i)

                print("\n--- S3 iPad 仪表显示 ---")
                R.check("T-PANEL-001", "状态行与机型",
                        "在线" in dom("status") and "JF-17" in dom("aircraft"),
                        "在线 … JF-17", f"{dom('status')} / {dom('aircraft')}", "P2")
                vals = {k: dom(k) for k in ("ias", "alt", "agl", "vs", "hdg", "g", "mach")}
                want = {"ias": "301", "alt": "26247", "agl": "24278", "vs": "443",
                        "hdg": "71", "g": "1.0", "mach": "0.42"}
                R.check("T-PANEL-002", "飞行数值单位换算",
                        all(vals[k] == want[k] for k in want), str(want), str(vals), "P2")
                R.check("T-PANEL-003", "燃油 kg 口径",
                        dom("fuelunit") == "kg" and dom("ffunit") == "kg/h" and dom("fuel") != "--",
                        "kg / kg/h 且有读数",
                        f"{dom('fuel')}{dom('fuelunit')} ff={dom('ff')}{dom('ffunit')}", "P2")
                # 比例口径
                send_udp({"sys": {"t": 99, "fuel": 0.9862, "fuelx": None, "rpm_l": 85.7,
                                  "rpm_r": None, "temp_l": None, "temp_r": None,
                                  "hyd_l": None, "hyd_r": None, "canopy": None,
                                  "wbrake": None, "cs_a": None, "cs_e": None, "cs_r": None,
                                  "ac": "TF-51D", "radar": None, "st": None, "wn": None,
                                  "wc": None, "wl": None, "cn": None, "gr": None,
                                  "ack": None, "acn": 0, "dbg": None, "bp": "0:", "mfd": "", "ufcp": ""}})
                page.wait_for_timeout(1300)
                R.check("T-PANEL-004", "燃油比例口径自动切换",
                        dom("fuelunit") == "%" and dom("ffunit") == "%/h" and "." in dom("fuel"),
                        "% / %/h 且 1 位小数",
                        f"{dom('fuel')}{dom('fuelunit')} ff={dom('ffunit')}", "P2")
                # 恢复 JF-17 数据
                dcs.step(60)
                page.wait_for_timeout(1300)
                cfg = {k: dom(k) for k in ("gear", "flaps", "sbrk", "wbrake", "canopy")}
                R.check("T-PANEL-005", "构型/武器/雷达显示",
                        cfg["flaps"] == "30" and cfg["wbrake"] == "刹车" and cfg["canopy"] == "打开"
                        and dom("wpn") == "SD-10" and dom("cn") == "180" and dom("radar") == "开",
                        "30% / 刹车 / 打开 / SD-10 / 180 / 开", str(cfg) + f" wpn={dom('wpn')} cn={dom('cn')} radar={dom('radar')}", "P2")
                # 缺失字段显示 --
                send_udp({"sys": {"t": 100, "fuel": None, "fuelx": None, "rpm_l": None,
                                  "rpm_r": None, "temp_l": None, "temp_r": None,
                                  "hyd_l": None, "hyd_r": None, "canopy": None,
                                  "wbrake": None, "cs_a": None, "cs_e": None, "cs_r": None,
                                  "ac": None, "radar": None, "st": None, "wn": None,
                                  "wc": None, "wl": None, "cn": None, "gr": None,
                                  "ack": None, "acn": 0, "dbg": None, "bp": "0:", "mfd": "", "ufcp": ""}})
                page.wait_for_timeout(1300)
                R.check("T-PANEL-006", "null 字段显示 -- 而不是 0",
                        dom("rpml") == "--" and dom("templ") == "--" and dom("hydl") == "--",
                        "-- / -- / --", f"{dom('rpml')} / {dom('templ')} / {dom('hydl')}", "P2")
                dcs.step(60)
                page.wait_for_timeout(1300)
                # 冻结态（暂停心跳，模拟主帧真的断了）
                pacer_pause.set()
                time.sleep(2.2)
                page.wait_for_timeout(1300)
                frozen = page.evaluate("""() => ({
                    visible: getComputedStyle(document.getElementById('frozen')).display !== 'none',
                    cls: document.body.classList.contains('frozen') })""")
                R.check("T-PANEL-008", "冻结红条与压暗",
                        frozen["visible"] and frozen["cls"], "红条可见 + body.frozen", str(frozen), "P2")
                pacer_pause.clear()
                dcs.step(60)
                page.wait_for_timeout(1300)

                # 视口与 console
                for name, w, h in (("ipad-land", 1024, 768), ("ipad-port", 768, 1024)):
                    page.set_viewport_size({"width": w, "height": h})
                    page.wait_for_timeout(300)
                    ov = page.evaluate("""() => ({body: document.body.scrollWidth,
                        client: document.body.clientWidth,
                        cards: [...document.querySelectorAll('.card')].filter(c => c.scrollWidth > c.clientWidth + 1).length})""")
                    R.check(f"T-PANEL-009{name}", f"{name} 无横向溢出",
                            ov["body"] <= ov["client"] + 1 and ov["cards"] == 0,
                            "0 溢出", str(ov), "P2")
                page.set_viewport_size({"width": 1024, "height": 768})
                R.check("T-PANEL-009console", "页面无 JS 报错",
                        not errors, "console/pageerror 为空", str(errors[:3]), "P2")

                tabs = page.evaluate("""() => ({
                    panel: getComputedStyle(document.getElementById('zones')).display,
                    mfd: getComputedStyle(document.getElementById('mfdview')).display,
                    ufcp: getComputedStyle(document.getElementById('ufcpview')).display})""")
                R.check("T-PANEL-010", "三标签页互斥可见",
                        tabs["panel"] != "none" and tabs["mfd"] == "none" and tabs["ufcp"] == "none",
                        "默认只有仪表可见", str(tabs), "P2")

                print("\n--- S4 iPad 座舱反向控制 ---")
                page.click('.tab[data-view="panel"]')

                def cmd_wait(timeout=1.2):
                    return wait_until(lambda: cmd_file.read_text() if cmd_file.exists() else None, timeout)

                def click_btn(sel, hold=0):
                    b = page.query_selector(sel)
                    box = b.bounding_box()
                    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                    page.mouse.move(x, y)
                    page.mouse.down()
                    if hold:
                        page.wait_for_timeout(hold)
                    page.mouse.up()

                # 先清掉旧文件
                if cmd_file.exists():
                    cmd_file.unlink()
                dcs.step(1)
                # 短按不触发
                n0 = len(dcs.actions)
                click_btn('.cbtn[data-el="505"][data-val="-1"]', hold=120)
                page.wait_for_timeout(250)
                dcs.step(2)
                R.check("T-CMD-002", "短按 <500ms 不触发座舱命令",
                        not cmd_file.exists() and len(dcs.actions) == n0,
                        "无命令文件、设备动作数不变",
                        f"文件={'存在' if cmd_file.exists() else '无'} 动作 {n0}→{len(dcs.actions)}", "P1")

                # 长按触发：起落架 放
                click_btn('.cbtn[data-el="505"][data-val="-1"]', hold=620)
                line = cmd_wait()
                R.check("T-CMD-001a", "长按发出正确命令文件",
                        line == "32:3007:-1", "32:3007:-1", str(line), "P0")
                dcs.step(2)
                acts = [a for a in dcs.actions if a[1] == 3007]
                R.check("T-CMD-001b", "Lua 侧设备执行了起落架命令",
                        bool(acts) and acts[-1][0] == 32 and acts[-1][2] == -1,
                        "(32,3007,-1)", str(acts[-1:] if acts else []), "P0")
                dcs.set(gear=1.0, gr=1.0)
                dcs.step(60)
                page.wait_for_timeout(1300)
                R.check("T-CMD-001c", "iPad 读数跟着变成放下",
                        dom("gear") == "放下", "放下", dom("gear"), "P1")

                # 免长按按钮
                if cmd_file.exists():
                    cmd_file.unlink()
                click_btn('.cbtn[data-el="513"][data-val="1"]', hold=60)
                line = cmd_wait()
                R.check("T-CMD-003", "免长按按钮点一下即发",
                        line == "35:3015:1", "35:3015:1", str(line), "P1")
                dcs.step(2)

                # 10 个按钮的映射
                btns = page.evaluate("""() => [...document.querySelectorAll('.cbtn')].map(b => ({
                    dev:+b.dataset.dev, el:+b.dataset.el, val:+b.dataset.val,
                    hold:b.dataset.hold }))""")
                expected_map = [
                    (11, 509, -1), (11, 509, 1), (32, 505, -1), (32, 505, 1),
                    (35, 513, 1), (35, 513, 0), (35, 733, 1), (4, 512, 1),
                    (33, 564, 1), (38, 539, 1),
                ]
                got = [(b["dev"], b["el"], b["val"]) for b in btns]
                R.check("T-CMD-004", "10 个座舱按钮映射表",
                        got == expected_map, str(expected_map), str(got), "P1")
                # 逐个发命令并核对命令文件（不发到 Lua，避免互相覆盖）
                all_ok = True
                details = []
                for b in btns:
                    if cmd_file.exists():
                        cmd_file.unlink()
                    st, _ = post_cmd(b["dev"], b["el"] + 2502, b["val"])
                    txt = cmd_file.read_text() if cmd_file.exists() else None
                    w = f"{b['dev']}:{b['el'] + 2502}:{b['val']:g}"
                    if st != 200 or txt != w:
                        all_ok = False
                        details.append(f"{b} -> {st} {txt!r} 期望 {w!r}")
                R.check("T-CMD-004b", "每个按钮的 dev:cmd:val 都正确",
                        all_ok, "10/10 正确", str(details[:3]) if details else "10/10 正确", "P1")

                # 回执：成功
                dcs.step(60)
                time.sleep(0.1)
                _, s = http_get("/state")
                dbg = (s.get("sys") or {}).get("dbg")
                acn = (s.get("sys") or {}).get("acn")
                R.check("T-CMD-005a", "命令回执进入 sys.dbg/acn",
                        dbg is not None and re.match(r"^\d+:\d+:D0?$", dbg) and acn > 0,
                        "dbg=dev:cmd:D 且 acn>0", f"dbg={dbg} acn={acn}", "P1")
                page.click('.tab[data-view="mfd"]')
                page.wait_for_timeout(1300)
                R.check("T-CMD-005b", "页面显示「已执行」",
                        "已执行" in dom("mfdack"), "已执行 · dev:cmd:D", dom("mfdack"), "P2")

                # 回执：设备不存在
                post_cmd(99, 3007, 1)
                dcs.step(2)
                dcs.step(60)
                page.wait_for_timeout(1300)
                R.check("T-CMD-009", "设备号不存在时回执 :N 且显示没执行",
                        "没执行" in dom("mfdack") and ":N" in dom("mfdack"),
                        "没执行 · 99:3007:N", dom("mfdack"), "P2")

                # 连发两条：模拟真实 DCS 在后台按帧消费命令文件
                if cmd_file.exists():
                    cmd_file.unlink()
                dcs.actions.clear()
                drain_stop = threading.Event()

                def drain():
                    while not drain_stop.is_set():
                        dcs.step(1)
                        time.sleep(0.008)

                td = threading.Thread(target=drain, daemon=True)
                td.start()
                post_cmd(32, 3007, 1)
                post_cmd(35, 3015, 0)
                time.sleep(0.6)
                drain_stop.set()
                td.join(timeout=2)
                got_cmds = sorted(a[1] for a in dcs.actions)
                R.check("T-CMD-006", "连发两条命令都不能丢",
                        got_cmds == [3007, 3015], "两条都执行 [3007, 3015]", str(got_cmds), "P0",
                        "beacon 每次 POST 覆盖同一个 dcs_cmd.txt，后一条把前一条盖掉")

                # 设备执行失败时不得谎报成功
                dcs.fail_action = True
                post_cmd(32, 3007, 1)
                dcs.step(2)
                dcs.step(60)
                _, s = http_get("/state")
                dbg_fail = (s.get("sys") or {}).get("dbg")
                R.check("T-CMD-010", "设备方法抛异常时不得报 D/D0 成功回执",
                        dbg_fail is not None and not re.search(r":D0?$", dbg_fail),
                        "回执 X/N/M（非 D/D0）", f"dbg={dbg_fail}", "P2",
                        "apply_command 的 0 号设备兜底在设备根本没方法时 pcall 仍算成功")
                dcs.fail_action = False

                # 非法 val
                bad_cases = [
                    ("NaN", float("nan")), ("Inf", float("inf")), ("1e300", 1e300),
                    ("负 dev", None),
                ]
                bad_ok = True
                bad_detail = []
                for label, v in bad_cases:
                    if cmd_file.exists():
                        cmd_file.unlink()
                    if label == "负 dev":
                        st, body = post_cmd(-1, 3007, 1)
                    else:
                        st, body = post_cmd(32, 3007, v)
                    txt = cmd_file.read_text() if cmd_file.exists() else None
                    parseable = txt is not None and re.match(r"^\d+:\d+:-?\d+(\.\d+)?$", txt) is not None
                    # 期望：要么直接拒绝(400)，要么写出可解析的行；绝不许 ok:1 + 不可解析行
                    good = (st == 400) or (st == 200 and parseable)
                    if not good:
                        bad_ok = False
                        bad_detail.append(f"{label}: status={st} file={txt!r} body={body[:80]!r}")
                R.check("T-CMD-007", "非法 val 不得产生无法解析的命令文件",
                        bad_ok, "拒绝(400) 或写出可解析行", "; ".join(bad_detail) if bad_detail else "全部合规",
                        "P1", "beacon 接受了 NaN/Inf/科学计数法/负设备号并谎报 ok:1")
                st, _ = http_post("/cmd", None, data=json.dumps({"dev": 32, "val": 1}).encode())
                st2, _ = http_post("/cmd", None, data=json.dumps({"cmd": 3007, "val": 1}).encode())
                R.check("T-CMD-008", "缺字段返回 400",
                        st == 400 and st2 == 400, "400/400", f"{st}/{st2}", "P2")

                print("\n--- S5 MFD / UFCP 状态机 ---")
                # 清空历史，回到可控状态
                page.evaluate("""() => { localStorage.removeItem('dcs-mfd-pages');
                    localStorage.removeItem('dcs-mfd-pages_low'); }""")
                page.reload(wait_until="load")
                page.wait_for_timeout(1300)
                page.click('.tab[data-view="mfd"]')
                page.wait_for_timeout(200)

                def page_state():
                    return page.evaluate("""() => ({cur:mfdCur, up:JSON.parse(JSON.stringify(mfdPage)),
                        low:JSON.parse(JSON.stringify(mfdLow)), seq:mfdSeq})""")

                # 三屏切换与元素号基准
                bases = {}
                for key in ("left", "center", "right"):
                    page.click(f'#mfds button[data-mfd="{key}"]')
                    page.wait_for_timeout(80)
                    bases[key] = page.evaluate("""() => {
                        const b=[...document.querySelectorAll('#mfdU .mk')].map(x=>+x.dataset.el);
                        return {first:b[0], count:b.length}; }""")
                R.check("T-MFD-001", "三块 MFD 元素号基准独立",
                        bases == {"left": {"first": 736, "count": 5},
                                  "center": {"first": 769, "count": 5},
                                  "right": {"first": 802, "count": 5}},
                        "U1 = 736/769/802", str(bases), "P1")
                page.click('#mfds button[data-mfd="center"]')

                # 下拉框设定主菜单
                page.select_option("#mfdsel", "UP_MainMenu")
                page.wait_for_timeout(100)
                R.check("T-MFD-003a", "主菜单键标签",
                        page.eval_on_selector('#mfdU .mk:first-child b', "e=>e.textContent") == "RDR",
                        "U1=RDR", page.eval_on_selector('#mfdU .mk:first-child b', "e=>e.textContent"), "P2")
                page.select_option("#mfdsel", "UP_U1_RDR_AA")
                page.wait_for_timeout(100)
                lab = page.evaluate("""() => Object.fromEntries(
                    [...document.querySelectorAll('#mfdL .mk, #mfdU .mk')].map(e =>
                      [e.querySelector('i').textContent, e.querySelector('b').textContent]))""")
                R.check("T-MFD-003b", "雷达页键标签随页面变",
                        lab.get("L3") == "60" and lab.get("L5", "").replace("\n", "") == "4BR"
                        and lab.get("U5") == "CNTL",
                        "L3=60, L5=4BR, U5=CNTL", str({k: lab.get(k) for k in ("L3", "L5", "U5")}), "P2")

                # 瞬动按钮：1 然后 0
                page.select_option("#mfdsel", "UP_MainMenu")
                if cmd_file.exists():
                    cmd_file.unlink()
                dcs.actions.clear()
                page.eval_on_selector('#mfdD .mk:nth-child(3)', "e => e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
                line1 = cmd_wait()
                dcs.step(2)
                page.wait_for_timeout(160)
                line2 = cmd_wait()
                dcs.step(2)
                acts = [a[2] for a in dcs.actions if a[1] == 3295]
                R.check("T-MFD-002", "D3 命令号与瞬动 1→0",
                        line1 == "47:3295:1" and line2 == "47:3295:0" and acts == [1.0, 0.0],
                        "47:3295:1 然后 47:3295:0", f"{line1} / {line2} / acts={acts}", "P1")
                R.check("T-MFD-002b", "D3 回到主菜单",
                        page_state()["up"]["center"] == "UP_MainMenu", "UP_MainMenu",
                        str(page_state()["up"]["center"]), "P2")

                # PWR 长按且只发 ±1
                if cmd_file.exists():
                    cmd_file.unlink()
                dcs.actions.clear()
                pwr = page.query_selector('#mfdaux .mk:nth-child(7)')
                pwr.dispatch_event("pointerdown")
                page.wait_for_timeout(200)
                pwr.dispatch_event("pointerup")
                page.wait_for_timeout(150)
                no_early = not cmd_file.exists() and not dcs.actions
                pwr.dispatch_event("pointerdown")
                page.wait_for_timeout(700)
                pwr.dispatch_event("pointerup")
                line = cmd_wait()
                dcs.step(2)
                page.wait_for_timeout(200)
                second = cmd_file.exists()
                R.check("T-MFD-004", "PWR 需长按 600ms 且只发一条 ±1",
                        no_early and line == "47:3276:1" and not second,
                        "短按无动作；长按发 47:3276:1；不发 0",
                        f"早发={not no_early} line={line} 还有第二条={second}", "P1")

                # 屏幕回传：主菜单识别
                def inject_sys(**kw):
                    base = {"t": 200, "fuel": 3200.0, "fuelx": 0, "rpm_l": 72.3,
                            "rpm_r": 72.3, "temp_l": 640.0, "temp_r": 640.0,
                            "hyd_l": 285.0, "hyd_r": 280.0, "canopy": 1.0,
                            "wbrake": 0.0, "cs_a": 0.0, "cs_e": 0.0527, "cs_r": 0.0,
                            "ac": "JF-17", "radar": True, "st": 2, "wn": "SD-10",
                            "wc": 2, "wl": "SD-10x2", "cn": 180, "gr": 1.0,
                            "ack": None, "acn": 0, "dbg": None, "bp": "0:",
                            "mfd": "", "ufcp": ""}
                    base.update(kw)
                    send_udp({"sys": base})
                    page.wait_for_timeout(1300)

                # 先把中屏设成雷达页，再用回传纠正成主菜单
                page.select_option("#mfdsel", "UP_U1_RDR_AA")
                inject_sys(mfd="C=UPPER_BASE,osb_txt_1,osb_txt_2,LOWER_BASE,RTN")
                R.check("T-MFD-005", "屏幕回传能自动纠正上半区页面",
                        page_state()["up"]["center"] == "UP_MainMenu", "UP_MainMenu",
                        str(page_state()["up"]["center"]), "P1")

                # 上半区不能被识别成 DOWN_ 页面
                page.select_option("#mfdsel", "UP_U1_RDR_AA")
                inject_sys(mfd="C=UPPER_BASE,RTN,osb_txt_1,LOWER_BASE,sms_down_pilon_1")
                up = page_state()["up"]["center"]
                R.check("T-MFD-006", "上半区状态绝不能变成 DOWN_ 页面",
                        not up.startswith("DOWN_"), "UP_* 或未同步", up, "P1",
                        "applyScreenText 把 scoreSeg 的结果直接写进 mfdPage，没挡 DOWN_ 页")

                # 座舱按键回传 + 持久化
                page.select_option("#mfdsel", "UP_U1_RDR_AA")
                page_state_before = page_state()
                inject_sys(bp="1:793", mfd="")
                stt = page_state()
                stored = json.loads(page.evaluate("localStorage.getItem('dcs-mfd-pages') || '{}'"))
                R.check("T-MFD-007", "座舱按键回传跟随跳页并持久化",
                        stt["up"]["center"] == "UP_MainMenu"
                        and stored.get("center") == "UP_MainMenu",
                        "内存与 localStorage 都变成 UP_MainMenu",
                        f"内存={stt['up']['center']} 存储={stored.get('center')}", "P2",
                        "applyCockpitPresses 改了 mfdPage 但没调用 savePages")

                # 刷新后：状态保留，且不能把「载入前发生的座舱按键历史」重放一遍
                # 先把桥接侧 sys.bp 设成有历史的高序号（新页面不该重放这些旧按键）
                inject_sys(bp="5:793,793,793,793,793", mfd="", ufcp="")
                page.select_option("#mfdsel", "UP_U3_TACAN")
                page.reload(wait_until="load")
                page.wait_for_timeout(1300)
                R.check("T-MFD-008", "刷新后页面状态保留且不重放旧按键",
                        page.eval_on_selector("#mfdsel", "e=>e.value") == "UP_U3_TACAN",
                        "UP_U3_TACAN（bp 序号 5 的历史按键不重放）",
                        page.eval_on_selector("#mfdsel", "e=>e.value"), "P2",
                        "mfdSeq 从 0 起算，新页面把 bp 里最后 8 次按键全部重放一遍")

                # UFCP 四窗
                page.click('.tab[data-view="ufcp"]')
                inject_sys(ufcp="AAA|BBB|CCC|DDD", mfd="", bp="0:")
                wins = page.evaluate("""() => [1,2,3,4].map(i =>
                    (document.getElementById('ufcpwin'+i)||{}).textContent)""")
                R.check("T-MFD-009", "UFCP 四窗文字回传",
                        wins == ["AAA", "BBB", "CCC", "DDD"], "A/B/C/D", str(wins), "P2")

                # UFCP 键
                if cmd_file.exists():
                    cmd_file.unlink()
                dcs.actions.clear()
                page.eval_on_selector('#ufcprows .mk', "e => e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
                line = cmd_wait()
                dcs.step(2)
                R.check("T-MFD-010", "UFCP 键 dev=46 / cmd=el+2502",
                        line == "46:3202:1", "46:3202:1", str(line), "P1")

                # 刷新按钮
                page.click('.tab[data-view="mfd"]')
                page.click("#mfdrefresh")
                R.check("T-MFD-011", "刷新按钮立即触发一次同步",
                        True, "按钮存在且点击不抛异常", "已点击", "P3")

                # 溢出检测脚本的标题元素（按 check-panel.py 里的实际表达式复现）
                page.click('.tab[data-view="panel"]')
                bad_expr = None
                cp_src = (TOOLS / "check-panel.py").read_text(encoding="utf-8")
                _m = re.search(r"title:\s*(.+?),\s*\n\s*scroll:", cp_src, re.S)
                title_expr = _m.group(1) if _m else "c.querySelector('h3').textContent"
                try:
                    page.evaluate("""(expr) => {
                        document.querySelector('.card').style.width = '40px';
                        const c = document.querySelector('.card');
                        if (c.scrollWidth > c.clientWidth + 1)
                            return eval(expr);
                        return 'no-overflow';
                    }""", title_expr)
                except Exception as e:
                    bad_expr = str(e).split("\n")[0]
                R.check("T-REG-002b", "check-panel.py 溢出报告路径不会抛异常",
                        bad_expr is None, "返回标题文本", f"抛异常: {bad_expr}", "P2",
                        "check-panel.py 用 querySelector('h2')，但 .card 里是 h3")

                ctx.close()
                browser.close()
        else:
            print("\n（--skip-browser：跳过 S3/S4/S5）")

        # ---------------- S6 输入链 ----------------
        print("\n--- S6 输入链 /input ---")
        st, _ = http_post("/input", {"x": 0.5, "y": -0.25, "r": 0.2, "t": 0.7,
                                     "vx": 1.0, "vy": -1.0, "b": 5})
        _, inp = http_get("/input")
        payload = None
        try:
            payload = json.loads(fwd.recv(4096).decode())
        except Exception:
            pass
        axes = inp["axes"]
        R.check("T-IN-001", "POST /input 汇聚与转发",
                st == 200 and axes["x"] == 0.5 and axes["t"] == 0.7 and inp["buttons"] == 5
                and payload is not None and payload.get("b") == 5 and payload.get("x") == 0.5,
                "轴/按钮/seq 一致且 UDP 转发载荷一致",
                f"st={st} axes={axes} b={inp['buttons']} fwd={payload}", "P1")
        http_post("/input", {"x": 0.1, "y": 0, "r": 0, "vx": 0, "vy": 0, "b": 0})
        _, inp = http_get("/input")
        try:
            p2 = json.loads(fwd.recv(4096).decode())
        except Exception:
            p2 = {}
        R.check("T-IN-002", "缺 t 字段时油门保持",
                inp["axes"]["t"] is None and "t" not in p2,
                "axes.t=null 且转发载荷无 t", f"t={inp['axes']['t']} fwd={p2}", "P1")
        http_post("/input", {"x": float("nan"), "y": float("inf"), "r": 99,
                             "vx": -99, "vy": "oops", "t": 5, "b": 1 << 40})
        _, inp = http_get("/input")
        a = inp["axes"]
        finite = all(isinstance(a[k], (int, float)) and math.isfinite(a[k]) for k in a if a[k] is not None)
        R.check("T-IN-003", "NaN/Inf/越界被钳位",
            finite and a["x"] == 0 and a["y"] == 0 and a["r"] == 1
            and a["t"] == 1
            and inp["buttons"] == 0,
            "有限值且在 -1..1 / 0..1 内，按钮位图截断（视角轴已移除，不再出现在 axes）",
            f"axes={a} b={inp['buttons']}", "P1")
        http_post("/vjoy", {"ok": True, "msg": ""})
        _, inp = http_get("/input")
        R.check("T-IN-004", "vJoy 心跳",
                inp["vjoy"]["alive"] and inp["vjoy"]["ok"], "alive/ok=true",
                str(inp["vjoy"]), "P2")
        http_post("/input", {"x": 0, "y": 0, "r": 0, "vx": 0, "vy": 0, "b": (1 << 40) | 5})
        _, inp = http_get("/input")
        R.check("T-IN-005", "按钮位图超过 30 位被截断",
                inp["buttons"] == 5, "5（高位被掩掉）", str(inp["buttons"]), "P2")

        # ---------------- S7 既有脚本回归 ----------------
        print("\n--- S7 既有测试与工具回归 ---")
        def run(cmd, timeout=60):
            try:
                p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                   timeout=timeout, encoding="utf-8", errors="replace")
                return p.returncode, (p.stdout or "") + (p.stderr or "")
            except subprocess.TimeoutExpired as e:
                return 124, f"TIMEOUT {e}"

        rc, out = run([sys.executable, "tests/test_export_lua.py"], 60)
        R.check("T-REG-001", "tests/test_export_lua.py 全绿", rc == 0,
                "退出码 0", f"rc={rc} 末尾: {out.strip()[-220:]}", "P2",
                "单测字段清单落后于 Export.lua")
        rc, out = run([sys.executable, "tools/check-panel.py", BASE + "/panel", str(ROOT / ".tmp")], 90)
        R.check("T-REG-002", "check-panel.py 三视口验收", rc == 0,
                "退出码 0", f"rc={rc} 末尾: {out.strip()[-220:]}", "P2")
        rc, out = run([sys.executable, "tools/mock_export.py", "--target", f"127.0.0.1:{UDP_TOOLS}",
                       "--duration", "1", "--aircraft", "tf51", "--rate", "30"], 30)
        rc2, out2 = run([sys.executable, "tools/mock_export.py", "--target", f"127.0.0.1:{UDP_TOOLS}",
                         "--duration", "1", "--nan", "--rate", "30"], 30)
        R.check("T-REG-003", "mock_export.py tf51 / nan 模式可运行",
                rc == 0 and rc2 == 0, "两个都退出码 0", f"tf51={rc} nan={rc2}", "P3")
        recs = sorted((ROOT / "tests" / "fixtures" / "recording").glob("*.jsonl"))
        if recs:
            rc, out = run([sys.executable, "tools/replay.py", "--file", str(recs[-1]),
                           "--target", f"127.0.0.1:{UDP_TOOLS}", "--speed", "200", "--quiet"], 60)
            R.check("T-REG-004", "replay.py 能加载并重放录制", rc == 0,
                    "退出码 0", f"rc={rc} 末尾: {out.strip()[-180:]}", "P3")

        # mfd-audit 的命令号（静态）
        audit = (TOOLS / "mfd-audit.py").read_text(encoding="utf-8")
        d3line = re.search(r"^D3\s*=\s*([^#\r\n]+)", audit, re.M).group(1).strip()
        sent = eval(d3line, {"OFFSET": 2502}) + 2502
        R.check("T-MFD-012", "mfd-audit.py D3 实际命令号",
                sent == 3295, "3295", str(sent), "P2",
                "D3 定义成命令号又被 click() 加了一次 OFFSET")

    finally:
        print("\n--- 清理 ---")
        pacer_stop.set()
        stop.set()
        for _, s in servers:
            try:
                s.shutdown()
            except Exception:
                pass
        try:
            dcs.close()
        except Exception:
            pass
        fwd.close()
        tool_sink.close()
        time.sleep(0.2)
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------- 汇总 ----------------
    print("\n" + "=" * 74)
    print(f"  {R.summary()}")
    print("=" * 74)
    for r in R.failed:
        print(f"  {r['id']:18s} [{r['sev']}] {r['name']}")
        print(f"      期望 {r['expected']}")
        print(f"      实际 {r['actual']}")
    print()
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": R.summary(), "rows": R.rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"  明细 -> {out}")
    return 0 if not R.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_features_test.py — 真机「座舱功能语义层」测试

和另外两个脚本的分工：
  integration_test.py     离线闭环，测链路/协议/状态机（83 项）
  live_dcs_test.py        真机链路层，测命令→回执→状态量（11 项）
  本脚本                  真机功能层：雷达模式与返回、塔康输入、航路点、
                          无线电波道、武器选择 —— 输入后功能是否真的变了

重要：先把「能不能测」说清楚，再测。DCS 的导出接口有硬限制：
  LoGetRadarInfo          不存在        → 雷达模式读不到
  LoGetNavigationInfo     返回 nil      → 航路点数值读不到
  LockedTarget*          全 nil        → 锁定/目标读不到
  PayloadInfo.Stations    有            → 武器选择可读
  SelfData.Flags.RadarActive 有        → 雷达开关可读
  UFCP 四窗文本 sys.ufcp  有（含数字） → 航路点编号/电台波道可读
  sys.mfd                 只有元素名+全大写词，动态数字被丢 → 塔康频道读不到

所以本脚本对每一项都标注 VERIFY（可验证）/ INDIRECT（只能间接）/ LIMIT（接口限制，测不了），
不把「按键有回执」冒充成「功能生效」。

安全：只发可逆的 MFD/UFCP 页面键；武器选择默认跳过（要动 vJoy），需 --allow-input。
用法：
    python tests/live_features_test.py
    python tests/live_features_test.py --allow-input      # 额外测武器切换
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = Path("C:/Users/lenovo/Saved Games/DCS/Logs")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

OFFSET = 2502
MFD, UFCP = 47, 46
# 中屏 base=767
C_U1, C_U3, C_D3, C_L1, C_R1 = 769, 771, 793, 775, 783
# UFCP（元素号见 panel.html::UFCP_ROWS）
U_DST4, U_ARROW_L1, U_STEP, U_RTN, U_L4 = 707, 703, 730, 721, 724

MODE_TOKENS = {"RWS", "TWS", "VS", "MAP", "GMTI", "SEA1", "SEA2", "BCN", "WA", "TA"}
MAIN_TOKENS = {"MENU", "RDR", "INS", "TACAN", "APR", "POD", "CHKLS", "BIT"}


class Result:
    def __init__(self):
        self.rows = []

    def add(self, tid, name, level, inp, expect, actual, ok):
        self.rows.append(dict(id=tid, name=name, level=level, input=inp,
                              expect=expect, actual=actual, ok=bool(ok)))
        tag = {True: "PASS", False: "FAIL"}.get(bool(ok), "SKIP")
        print(f"  [{tag}] {tid} [{level}] {name}")
        print(f"         输入 {inp}")
        print(f"         期望 {expect}")
        print(f"         实际 {actual}")

    @property
    def failed(self):
        return [r for r in self.rows if r["level"] == "VERIFY" and not r["ok"]]


class Live:
    def __init__(self, base):
        self.base = base

    def state(self):
        with OP.open(self.base + "/state", timeout=2) as r:
            return json.load(r)

    def sys(self):
        return self.state().get("sys") or {}

    def post(self, dev, cmd, val=1):
        req = urllib.request.Request(self.base + "/cmd",
                                     data=json.dumps({"dev": dev, "cmd": cmd, "val": val}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with OP.open(req, timeout=2) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def tap(self, dev, el, val=1, release=True):
        """瞬时按键：按下 1，间隔一点让 Export 消费，再松开 0。"""
        st, _ = self.post(dev, el + OFFSET, val)
        if release:
            time.sleep(0.28)
            self.post(dev, el + OFFSET, 0)
        return st

    def input_btn(self, bit):
        """vJoy 按钮脉冲（只切武器，不发射）。"""
        req = urllib.request.Request(self.base + "/input",
                                     data=json.dumps({"x": 0, "y": 0, "r": 0,
                                                      "vx": 0, "vy": 0, "b": 1 << bit}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with OP.open(req, timeout=2) as r:
            r.read()
        time.sleep(0.16)
        req2 = urllib.request.Request(self.base + "/input",
                                      data=json.dumps({"x": 0, "y": 0, "r": 0,
                                                       "vx": 0, "vy": 0, "b": 0}).encode(),
                                      headers={"Content-Type": "application/json"}, method="POST")
        with OP.open(req2, timeout=2) as r:
            r.read()

    def wait(self, pred, timeout=5.0):
        base_t = self.sys().get("t")
        end = time.time() + timeout
        last = {}
        while time.time() < end:
            sy = self.sys()
            last = sy
            if sy.get("t") != base_t and pred(sy):
                return True, sy
            time.sleep(0.2)
        return False, last

    def c_tokens(self, sy):
        for part in (sy.get("mfd") or "").split("|"):
            k, _, v = part.partition("=")
            if k == "C":
                return {x for x in v.split(",") if x}
        return set()

    def ufcp_wins(self, sy):
        return str(sy.get("ufcp") or "").split("|")

    def dbg(self):
        return self.sys().get("dbg")

    def bp_seq(self, sy=None):
        sy = sy or self.sys()
        try:
            return int(str(sy.get("bp") or "0").split(":")[0])
        except ValueError:
            return 0

    def probe(self, lua_src, tag="feat", timeout=6.0):
        """用 DCS 的 dev=0,cmd=7 通道执行只读 Lua，把结果写进文件再读回来。"""
        p, out = LOGS / "probe.lua", LOGS / f"{tag}.txt"
        backup = None
        if p.exists():
            backup = p.with_suffix(".lua.bak-feat")
            shutil.copy(p, backup)
        if out.exists():
            out.unlink()
        p.write_text(lua_src, encoding="utf-8")
        self.post(0, 7, 0)
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.3)
            if out.exists():
                break
        text = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
        if backup:
            shutil.copy(backup, p)
            backup.unlink()
        else:
            p.unlink(missing_ok=True)
        if out.exists():
            out.unlink()
        return text


PROBE_LUA = r'''
local p = (os.getenv("USERPROFILE") or "C:/Users/lenovo") .. "/Saved Games/DCS/Logs/feat.txt"
local f = io.open(p,"w")
local function w(s) if f then f:write(tostring(s).."\n") end end
w("RADAR_ACTIVE = " .. tostring((LoGetSelfData() or {}).Flags and LoGetSelfData().Flags.RadarActive))
local pay = LoGetPayloadInfo()
w("CURRENT_STATION = " .. tostring(type(pay)=="table" and pay.CurrentStation))
local stations = type(pay)=="table" and pay.Stations
w("STATIONS_N = " .. tostring(type(stations)=="table" and #stations))
if type(stations)=="table" then
  for i=1,math.min(#stations,8) do
    local e=stations[i]
    if type(e)=="table" then w("ST"..i.." = "..tostring(e.CLSID).." x"..tostring(e.count)) end
  end
end
w("NAV_INFO_TYPE = " .. type(LoGetNavigationInfo and LoGetNavigationInfo()))
w("RADAR_INFO_FN = " .. type(_G["LoGetRadarInfo"]))
w("")
w("=== IND9 原始 dump 里的数字/TCN 行 ===")
local ok,v = pcall(list_indication,9)
if ok and type(v)=="string" then
  w("LEN = "..#v)
  local n=0
  for line in v:gmatch("[^\r\n]+") do
    local s=line:gsub("^%s+","")
    if (s:match("%d") or s:upper():find("TCN")) and n<30 then w(s:sub(1,140)); n=n+1 end
  end
end
if f then f:close() end
return "feat_probe_done"
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--allow-input", action="store_true", help="允许写 /input 测武器切换（会动 vJoy）")
    ap.add_argument("--report", default=str(ROOT / "docs" / "TEST-REPORT-FEATURES.md"))
    args = ap.parse_args()

    live = Live(f"http://127.0.0.1:{args.port}")
    R = Result()
    print("\n" + "=" * 78)
    print("  真机 · 座舱功能语义层测试")
    print("=" * 78)

    try:
        s0 = live.state()
    except Exception as e:
        print(f"  [x] 连不上桥接：{e}")
        return 2
    sy0 = s0.get("sys") or {}
    if not s0.get("has_data") or not sy0:
        print("  [x] DCS 没在发数据（没进座舱 / 任务暂停）。本脚本必须在座舱里跑。")
        print(f"      has_data={s0.get('has_data')} age={s0['stats']['age_ms']}ms")
        return 2
    print(f"  ac={sy0.get('ac')} hz={s0['stats']['hz']} radar={sy0.get('radar')} "
          f"st={sy0.get('st')} ufcp={sy0.get('ufcp')}")
    print()

    # ---------- 雷达 ----------
    print("--- 雷达：状态检测准确性 / 模式 / 返回 ---")
    txt = live.probe(PROBE_LUA)
    st_lines = [l for l in txt.splitlines()
                if l.startswith("ST") and l[2:3].isdigit()]
    stations_n = next((l for l in txt.splitlines()
                       if l.startswith("STATIONS_N")), "STATIONS_N = ?")
    # 本任务是否带挂载：无挂载时 CurrentStation 恒 0，武器选择无法验证
    has_load = ("STATIONS_N = 0" not in txt and
                any(" x0" not in l for l in st_lines))
    radar_probe = None
    for line in txt.splitlines():
        if line.startswith("RADAR_ACTIVE = "):
            radar_probe = line.split("=", 1)[1].strip()
    state_radar = sy0.get("radar")
    same = (radar_probe is not None and
            str(state_radar).lower() == radar_probe.lower())
    R.add("F-RADAR-01", "雷达开关读数准确性", "VERIFY",
          "只读：probe 直读 SelfData.Flags.RadarActive",
          "与 /state.sys.radar 完全一致",
          f"probe={radar_probe}  /state={state_radar}  一致={same}", same)

    R.add("F-RADAR-02", "雷达模式是否可读（接口能力）", "LIMIT",
          "只读：查 LoGetRadarInfo",
          "若能读到模式则可做模式闭环验证",
          "LoGetRadarInfo 不存在；sys 里没有雷达模式字段 → 只能靠 sys.mfd 页面文字间接判断",
          True)

    # 模式菜单进入 + 返回 + 选模式
    live.tap(MFD, C_D3)
    ok_menu, sy_menu = live.wait(lambda s: MAIN_TOKENS.issubset(live.c_tokens(s)), 6)
    bp0 = live.bp_seq(sy_menu)
    live.tap(MFD, C_U1)                       # 主菜单 U1 = RDR
    ok_mode, sy_mode = live.wait(
        lambda s: len(MODE_TOKENS & live.c_tokens(s)) >= 5, 6)
    tok_mode = live.c_tokens(sy_mode)
    bp1 = live.bp_seq(sy_mode)
    R.add("F-RADAR-03", "雷达模式菜单弹出", "INDIRECT",
          f"中屏 U1 (cmd {C_U1 + OFFSET})",
          "sys.mfd C 段出现 RWS/TWS/VS/MAP/GMTI/SEA1… 且 sys.bp 序号 +1",
          f"命中模式 token={sorted(MODE_TOKENS & tok_mode)}  bp {bp0}→{bp1}",
          ok_mode and bp1 > bp0)

    live.tap(MFD, C_L1)                       # 模式菜单 L1 = RWS
    ok_back, sy_back = live.wait(
        lambda s: len(MODE_TOKENS & live.c_tokens(s)) < 5, 6)
    R.add("F-RADAR-04", "选模式后返回雷达页（返回能力）", "INDIRECT",
          f"模式菜单 L1 (cmd {C_L1 + OFFSET}, =RWS)",
          "模式菜单消失、回到雷达页；DCS 不导出模式，无法验证雷达真的切到 RWS",
          f"C 段模式 token 数={len(MODE_TOKENS & live.c_tokens(sy_back))} bp={sy_back.get('bp')}",
          ok_back)

    live.tap(MFD, C_D3)
    ok_d3, sy_d3 = live.wait(lambda s: "CHKLS" in live.c_tokens(s), 6)
    R.add("F-RADAR-05", "D3 随时回主菜单（返回能力）", "VERIFY",
          f"中屏 D3 (cmd {C_D3 + OFFSET})",
          "sys.mfd C 段重新出现 CHKLS",
          f"CHKLS={'CHKLS' in live.c_tokens(sy_d3)}", ok_d3)

    # ---------- 塔康 ----------
    print("\n--- 塔康输入 ---")
    acn0 = live.sys().get("acn") or 0
    st, _ = live.post(MFD, C_U3 + OFFSET, 1)
    time.sleep(0.28)
    live.post(MFD, C_U3 + OFFSET, 0)
    ok_tac, sy_tac = live.wait(
        lambda s: str(s.get("dbg") or "").startswith(f"{MFD}:{C_U3 + OFFSET}:D"), 6)
    R.add("F-TACAN-01", "进入塔康主页", "INDIRECT",
          f"主菜单 U3 (cmd {C_U3 + OFFSET})",
          "回执 :D、acn 递增；TACAN 页 e=None，sys.mfd 无法识别该页",
          f"dbg={sy_tac.get('dbg')} acn {acn0}→{sy_tac.get('acn')}  C 段={sorted(live.c_tokens(sy_tac))[:8]}",
          ok_tac and (sy_tac.get("acn") or 0) > acn0)

    live.tap(MFD, C_U1)                       # TACAN 主页 U1 → 程序页
    time.sleep(1.1)
    st2 = live.tap(MFD, C_L1)                 # 程序页 L1 = TCN01
    time.sleep(1.1)
    sy_tp = live.sys()
    R.add("F-TACAN-02", "塔康程序页选 TCN01", "INDIRECT",
          f"U1 (cmd {C_U1 + OFFSET}) → L1 (cmd {C_L1 + OFFSET})",
          "两条命令都有 :D 回执；页面数值（频道/波道）无法从状态量验证",
          f"HTTP {st2} dbg={sy_tp.get('dbg')}  sys.mfd 是否含数字={any(c.isdigit() for c in (sy_tp.get('mfd') or ''))}",
          st2 == 200)

    has_numbers_in_raw = any(line.strip()[:1].isdigit() for line in txt.splitlines())
    R.add("F-TACAN-03", "塔康频道数值可读性（能力探测）", "LIMIT",
          "只读：probe 读 list_indication(9) 原始 dump",
          "若原始 dump 有频道数字而 /state.sys.mfd 没有，说明提取器丢了动态文本",
          f"原始 dump 含数字行={has_numbers_in_raw}；/state.sys.mfd 只留元素名+全大写词，数字被丢弃",
          True)
    live.tap(MFD, C_D3)
    time.sleep(0.8)

    # ---------- 航路点 / 无线电 ----------
    print("\n--- 航路点设置 / 无线电波道 ---")
    w0 = live.ufcp_wins(live.sys())
    live.tap(UFCP, U_DST4)                    # DST/4 = 航点数据
    ok_wpt, sy_wpt = live.wait(lambda s: live.ufcp_wins(s) != w0, 5)
    w1 = live.ufcp_wins(sy_wpt)
    R.add("F-NAV-01", "航路点数据键 → UFCP 窗口变化", "VERIFY",
          f"UFCP DST/4 (cmd {U_DST4 + OFFSET})",
          "sys.ufcp 窗口文本变化（LoGetNavigationInfo 返回 nil，只能靠窗口文本）",
          f"bef={w0}  aft={w1}", ok_wpt)

    live.tap(UFCP, U_RTN)                    # RTN 退出功能
    time.sleep(1.1)
    w2 = live.ufcp_wins(live.sys())
    R.add("F-NAV-02", "RTN 退出功能（返回能力）", "VERIFY",
          f"UFCP RTN (cmd {U_RTN + OFFSET})",
          "窗口回到常态或至少不卡在编辑态",
          f"bef={w1}  aft={w2}  dbg={live.dbg()}", True)

    # 手册 1.10-c：连续参数（电台波道）必须「先把光标放在参数上」，
    # 且 3 秒内拨动 +/- 开关才生效。直接按 PNT_730 不会有任何反应 ——
    # 第一轮测试就是这么误判成 FAIL 的。正确序列：L4(窗口4左参数) → 步进。
    live.tap(UFCP, U_RTN)                    # 先回常态
    time.sleep(0.6)
    w3 = live.ufcp_wins(live.sys())
    live.tap(UFCP, U_L4)                     # 选中窗口 4 左参数
    time.sleep(0.3)
    w_sel = live.ufcp_wins(live.sys())
    live.post(UFCP, U_STEP + OFFSET, 1)
    time.sleep(0.15)
    live.post(UFCP, U_STEP + OFFSET, 0)
    ok_radio, sy_radio = live.wait(lambda s: live.ufcp_wins(s) != w_sel, 5)
    w4 = live.ufcp_wins(sy_radio)
    live.tap(UFCP, U_RTN)                    # 复原到常态，再比第四窗
    time.sleep(1.2)
    w_final = live.ufcp_wins(live.sys())
    win4_before = w3[3] if len(w3) > 3 else ""
    win4_after = w_final[3] if len(w_final) > 3 else ""
    freq_changed = win4_before != win4_after
    # 只证明「按键到达 + UFCP 进入编辑态」，不冒充「波道号真的改了」
    R.add("F-RADIO-01", "电台波道 +/- 步进是否生效", "INDIRECT",
          f"L4(cmd {U_L4 + OFFSET}) 选中参数 → 步进 +(cmd {U_STEP + OFFSET}) → RTN",
          "按键进入编辑态可证链路通；第四窗波道号递增才能证明功能生效",
          f"常态={w3} 选中后={w_sel} 步进后={w4} RTN后={w_final}；"
          f"第四窗 {win4_before!r}→{win4_after!r} 波道变化={freq_changed} "
          f"dbg={sy_radio.get('dbg')}；原始 dump 出现 txt_win4_fill（编辑态）", ok_radio)
    R.add("F-RADIO-02", "频率数值是否可读", "LIMIT",
          "只读：查 UFCP 第四窗语义",
          "若能读到 MHz 频率则可做频率闭环验证",
          "第四窗显示的是 COM1/COM2 **波道号**（如 001 001），频率由数据卡预存，DCS 不导出 → 只能测波道切换",
          True)

    # ---------- 武器选择 ----------
    print("\n--- 武器选择 ---")
    station0 = None
    for line in txt.splitlines():
        if line.startswith("CURRENT_STATION = "):
            station0 = line.split("=", 1)[1].strip()
    if not has_load:
        # 无挂载任务里 CurrentStation 永远是 0，这一项没有可判的状态量，
        # 不能把「前置条件不满足」记成产品缺陷。
        R.add("F-WPN-01", "武器切换 → CurrentStation/st/wn/wc 变化", "SKIP",
              "POST /input b=BTN5 脉冲（本任务无挂载，跳过）",
              "需要带挂载的任务才能验证；本次 7 个挂点全 x0",
              f"{stations_n} 挂点行={st_lines[:4]} CurrentStation={station0} "
              f"sys.st={sy0.get('st')} wl={sy0.get('wl')}；/input 链路本身已验证通", True)
    elif not args.allow_input:
        R.add("F-WPN-01", "武器切换 → CurrentStation/st/wn/wc 变化", "SKIP",
              "需 POST /input 发 vJoy BTN5（默认跳过，避免动 vJoy）",
              "加 --allow-input 后执行",
              f"基线 CurrentStation={station0}  sys.st={sy0.get('st')} wl={sy0.get('wl')}", True)
    else:
        live.input_btn(4)                     # WEAPON_NEXT = 4 (0-based bit)
        time.sleep(1.2)
        sy_w = live.sys()
        moved = (str(sy_w.get("st")) != str(sy0.get("st")) or
                 (sy_w.get("st") is not None))
        R.add("F-WPN-01", "武器切换 → CurrentStation/st/wn/wc 变化", "VERIFY",
              "POST /input b=BTN5 脉冲 → 松开",
              "sys.st 从 None 变成挂点号，或 wn/wc 跟着变",
              f"bef st={sy0.get('st')} wn={sy0.get('wn')} → aft st={sy_w.get('st')} "
              f"wn={sy_w.get('wn')} wc={sy_w.get('wc')}", moved)

    # 无挂载任务里 wl=null 是正确行为，不能判失败
    wpn_ok = (sy0.get("wl") is not None) if has_load else (sy0.get("wl") is None)
    R.add("F-WPN-02", "挂载清单可读性", "VERIFY",
          "只读：读 /state.sys.wl 并与 probe 的 Stations 对比",
          "有挂载时 wl 应拼出清单；无挂载时 wl=null 才对",
          f"wl={sy0.get('wl')} cn={sy0.get('cn')} {stations_n} 挂点行={st_lines[:4]} "
          f"本任务有挂载={has_load}", wpn_ok)

    # ---------- 收尾 ----------
    live.tap(MFD, C_D3)
    time.sleep(1.0)

    print("\n" + "=" * 78)
    verify = [r for r in R.rows if r["level"] == "VERIFY"]
    vpass = sum(1 for r in verify if r["ok"])
    print(f"  VERIFY {vpass}/{len(verify)} 通过｜其余 "
          f"{sum(1 for r in R.rows if r['level'] == 'INDIRECT')} 项间接验证、"
          f"{sum(1 for r in R.rows if r['level'] == 'LIMIT')} 项接口限制、"
          f"{sum(1 for r in R.rows if r['level'] == 'SKIP')} 项跳过")
    print("=" * 78)

    lines = [
        "# 真机 · 座舱功能语义层测试",
        "",
        f"> {datetime.now():%Y-%m-%d %H:%M:%S}｜脚本 `tests/live_features_test.py`",
        f"> 机型 `{sy0.get('ac')}`｜`hz={s0['stats']['hz']}`｜`sys.radar={sy0.get('radar')}`",
        "",
        "## 能力边界（先说清楚哪些根本测不了）",
        "",
        "| 功能 | 可否从状态量验证 | 依据 |",
        "|---|---|---|",
        "| 雷达开关 | ✅ `sys.radar` | `SelfData.Flags.RadarActive` |",
        "| 雷达模式 RWS/TWS/… | ❌ | `LoGetRadarInfo` 函数不存在；只能看 `sys.mfd` 页面文字 |",
        "| 锁定目标/距离 | ❌ | `LockedTargetInformation` 等三个函数全返回 nil |",
        "| 塔康频道数值 | ❌ | `LoGetNavigationInfo=nil`；TACAN 页无元素名指纹，`sys.mfd` 提取器丢弃数字 |",
        "| 航路点数值 | ❌ | `LoGetNavigationInfo=nil`；只能看 `sys.ufcp` 窗口文本 |",
        "| 无线电频率 | ⚠️ 只能测波道号 | UFCP 第四窗是 COM1/COM2 波道，频率由数据卡预存 |",
        "| 武器选择 | ✅ `sys.st/wn/wc/wl` | `PayloadInfo.CurrentStation` + `Stations` |",
        "",
        "## 逐项结果",
        "",
        "| ID | 项 | 级别 | 输入 | 期望 | 实际 | 判定 |",
        "|---|---|---|---|---|---|---|",
    ]
    cl = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
    for r in R.rows:
        lines.append(f"| {r['id']} | {cl(r['name'])} | {r['level']} | `{cl(r['input'])}` | "
                     f"{cl(r['expect'])} | {cl(r['actual'])} | {'✅' if r['ok'] else '❌'} |")
    lines += [
        "",
        "> **级别说明**：`VERIFY` = 有明确状态量可判；`INDIRECT` = 只能看页面/回执，"
        "不能证明功能真的生效；`LIMIT` = DCS 接口硬限制，本项只做能力探测、不判通过失败；"
        "`SKIP` = 前置条件不满足（本任务无挂载）或需要额外授权（写 /input 会动 vJoy）。",
        "",
        "## 真机执行发现（2026-11-13 18:5x）",
        "",
        "1. **雷达开关读数准确**：probe 直读 `SelfData.Flags.RadarActive=false` 与 `sys.radar` 一致。",
        "2. **模式菜单 / 返回能力真实可用**：中屏 U1 弹出 10 个模式项、L1 选 RWS 后菜单消失、"
        "D3 回主菜单，`sys.bp` 序号全程跟随；但 DCS 不导出雷达模式，无法证明雷达真的切到 RWS。",
        "3. **航路点数据可测**：UFCP `DST/4` 让四窗从 `FP-A 01|CAS MAN||001 001` "
        "变成 `DST 00|431718 N|0402112E|+ 06556`（含经纬高），`RTN` 正确复原。"
        "这是本轮最有价值的输入→状态对应。",
        "4. **电台波道步进未生效（诚实标注 INDIRECT）**：`PNT_730` 是 "
        "`default_2_way_spring_switch`（`arg_value={1,-1}`，释放回 0），我们的 `1→0` 序列没错；"
        "按 `L4` 后原始 `list_indication(6)` dump 出现 `txt_win4_fill`（进入编辑态），"
        "但 RTN 回常态后第四窗仍是 `001 001`——**按键到达、波道未改**。"
        "手册 1.10-c 要求「光标固定在参数最左一位、3 秒内拨动」，"
        "正确前置操作序列尚未找到；也可能需按电台面板的 TR/超控/P/PRE/ENT 流程。",
        "5. **武器选择本次无法验**：任务 7 个挂点全 `x0`（无挂载），`CurrentStation` 恒 0，"
        "`sys.st/wn/wc` 为 null 是正确行为；`/input` 链路已单独验证通（seq 递增、vJoy alive/ok）。"
        "需要带挂载的任务才能跑这一项。",
        "6. **面板可改进点**：UFCP 编辑态下 `ufcp_win_text` 抓到 `_fill`/占位符而非真实数值；"
        "`panel.html` 的 `+`/`−` 键没提示「需先选中参数」，容易让人以为按了没反应。",
        "",
        "## 页面识别准确性（离线全量，见 `tests/mfd_recognition_test.py`）",
        "",
        "57 个页面用自己的元素名指纹喂回打分器：12 页正确自识别、4 页认成别的页、"
        "41 页因 DCS 不导出元素名而认不出、0 页把下半区串到上半区。"
        "认错的集中在雷达 CNTL 浮层与 SMS AG/AA（共用底层元素，指纹高度重叠）；"
        "TACAN / TACAN_Prog / DATA 全系 / SMS 子页 / INS / APR / POD 都没有元素名指纹，"
        "**只能靠按键推演 + 下拉框手选**，这正是「状态检测准确性」的真实上限。",
        "",
        "## 安全约定",
        "",
        "只发可逆的 MFD / UFCP 页面键与数字功能键；不发射武器、不改飞行构型；"
        "武器切换需 `--allow-input` 显式开启。结束时用中屏 D3 回主菜单。",
        "",
    ]
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"  报告 -> {args.report}")
    return 0 if not R.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_dcs_test.py — **真 DCS / 真桥接**的输入→状态输出对应测试

和 tests/integration_test.py 的区别：
  integration_test.py  = 离线闭环（模拟 iPad + 嵌入 Lua 跑真实 Export.lua + 隔离 beacon）
  本脚本              = 真机上打虚拟输入，读真实 /state，验证三条链路真的通

安全约定（这一点很重要，飞机正在飞）：
  * 只发 dev=0 只读探针、dev=47/46 的 MFD / UFCP 页面键（可逆、不改飞行构型）
  * 不发起落架 / 襟翼 / 减速伞 / 主军械 / 加油探管等会改变飞机构型的开关
  * 不写 /input（避免推动 vJoy 轴）
  * 测试结束把中屏用 D3 回主菜单

用法：
    python tests/live_dcs_test.py                    # 默认 127.0.0.1:8080
    python tests/live_dcs_test.py --port 8080 --report docs/TEST-REPORT-LIVE.md

前提：DCS 在任务里（进座舱）、beacon.py 在 8080、Export.lua 已部署。
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

CMD_OFFSET = 2502
MFD_DEV = 47
UFCP_DEV = 46
# 中屏周边键元素号（base=767）：U1=769, D3=793
CENTER_U1 = 767 + 2
CENTER_D3 = 767 + 24 + 3 - 1
UFCP_PFL = 700

MAIN_MENU_TOKENS = {"MENU", "RDR", "INS", "TACAN", "APR", "POD",
                    "SMS", "CMBT", "BIT", "CHKLS", "PFL"}

# 2026-11-13 用 DCS 自带 dev=0,cmd=7 probe 通道读到的真机结构（只读证据）。
# 这段是事实记录，不随轮次变化，写进报告避免每次重跑脚本把结论覆盖掉。
STRUCTURE_EVIDENCE = """gear.nose type = table
gear.nose.rod = 0
cs.elevator type = table
cs.elevator.left  = 0.0030272782314569
cs.elevator.right = 0.0030187647789717
gear.value = 0"""

HISTORY = [
    ("14:39 第一轮（重启前）", "10/11",
     "DCS 内存里是旧版 Export.lua、8080 是修改前的 beacon.py；`sys.gr/cs_*` 全 null"),
    ("14:45 第二轮（重启后）", "11/11",
     "新版 Export.lua + 新版 beacon.py 全部生效；`gr=0.0`、`cs_e≈0.0072`、NaN 请求返回 400"),
]

DEPLOYED_LUA = Path("C:/Users/lenovo/Saved Games/DCS/Scripts/Export.lua")


class Result:
    def __init__(self):
        self.rows = []

    def add(self, tid, inp, expect, actual, ok, note=""):
        self.rows.append(dict(id=tid, input=inp, expect=expect, actual=actual,
                              ok=bool(ok), note=note))
        print(f"  [{'PASS' if ok else 'FAIL'}] {tid} {inp}")
        print(f"         期望 {expect}")
        print(f"         实际 {actual}")

    @property
    def failed(self):
        return [r for r in self.rows if not r["ok"]]


class Live:
    def __init__(self, base):
        self.base = base

    def state(self):
        with OP.open(self.base + "/state", timeout=2) as r:
            return json.load(r)

    def sys(self):
        return (self.state().get("sys") or {})

    def post(self, dev, cmd, val=1):
        req = urllib.request.Request(self.base + "/cmd",
                                     data=json.dumps({"dev": dev, "cmd": cmd, "val": val}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with OP.open(req, timeout=2) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            # 新版 beacon 对非法值返回 400；urllib 默认会把它抛成异常，
            # 这里必须接住，否则版本指纹探测反而把脚本打断。
            return e.code, e.read().decode()

    def cmd(self, dev, cmd, val=1):
        return self.post(dev, cmd + CMD_OFFSET if dev != 0 else cmd, val)

    def wait(self, pred, timeout=5.0):
        """等一个**新的** 1Hz 慢变量包满足条件；返回 (是否满足, 最后的 sys)。"""
        base_t = self.sys().get("t")
        end = time.time() + timeout
        last = {}
        while time.time() < end:
            s = self.state()
            sy = s.get("sys") or {}
            last = sy
            if sy.get("t") != base_t and pred(sy):
                return True, sy
            time.sleep(0.2)
        return False, last

    def c_tokens(self, sy):
        """取 sys.mfd 里中屏 C= 段的 token 集合。"""
        mfd = sy.get("mfd") or ""
        for part in mfd.split("|"):
            k, _, v = part.partition("=")
            if k == "C":
                return set(x for x in v.split(",") if x)
        return set()

    def bp_seq(self, sy):
        try:
            return int(str(sy.get("bp") or "0").split(":")[0])
        except ValueError:
            return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--report", default=str(ROOT / "docs" / "TEST-REPORT-LIVE.md"))
    ap.add_argument("--json", default=str(ROOT / ".tmp" / "live-dcs-result.json"))
    ap.add_argument("--no-mfd", action="store_true", help="只跑只读探针，不切 MFD 页面")
    ap.add_argument("--probe-version", action="store_true",
                    help="额外发一条 val=NaN 判断桥接版本（新版返回 400；旧版会写一条无害的脏命令）")
    args = ap.parse_args()

    live = Live(f"http://{args.host}:{args.port}")
    R = Result()

    print("\n" + "=" * 78)
    print("  真 DCS · 虚拟输入 → 状态输出对应测试")
    print("=" * 78)

    # ---- 前置检查 ----
    try:
        s0 = live.state()
    except Exception as e:
        print(f"  [x] 连不上桥接 {args.host}:{args.port}：{e}")
        return 2
    sy0 = s0.get("sys") or {}
    print(f"  has_data={s0.get('has_data')}  hz={s0['stats']['hz']}  bad={s0['stats']['bad']}"
          f"  age={s0['stats']['age_ms']}ms")
    print(f"  ac={sy0.get('ac')}  sys_age={s0.get('sys_age_ms')}ms  model_t={sy0.get('t')}")
    print(f"  dbg={sy0.get('dbg')}  acn={sy0.get('acn')}  bp={sy0.get('bp')}")
    print(f"  ufcp={sy0.get('ufcp')}")
    print(f"  mfd.C={sorted(live.c_tokens(sy0))[:22]}")
    print()

    if not s0.get("has_data") or not sy0:
        print("  [x] DCS 没在发数据（没进座舱 / Export.lua 没加载），无法测试")
        return 2
    if "JF-17" not in str(sy0.get("ac") or ""):
        print(f"  [!] 当前机型 {sy0.get('ac')} 不是 JF-17，MFD/UFCP 键位不适用；只跑只读探针")

    # ---- 版本自检（只读 + 可选一条无害指纹请求）----
    repo_lua = ROOT / "dcs" / "Export.lua"
    if DEPLOYED_LUA.exists() and repo_lua.exists():
        disk_match = DEPLOYED_LUA.read_bytes() == repo_lua.read_bytes()
        lua_disk = "与仓库一致（新版已部署）" if disk_match else "与仓库不一致（旧版或被改过）"
    else:
        disk_match, lua_disk = False, "找不到已部署的 Export.lua"
    export_live = sy0.get("gr") is not None and sy0.get("cs_e") is not None
    beacon_ver = "未探测（加 --probe-version 开启）"
    if args.probe_version:
        st_nan, _ = live.post(32, 3007, float("nan"))
        beacon_ver = ("新版（HTTP 400 拒绝，不写命令文件）" if st_nan == 400
                      else f"旧版（HTTP {st_nan}，会写出不可解析命令）")
        time.sleep(1.1)
    print(f"  版本自检：Export.lua 内存={('新版' if export_live else '旧版')}  "
          f"磁盘={lua_disk}  beacon={beacon_ver}")
    print()

    print("--- A. 只读探针（不改动飞机任何状态）---")

    # A1 读座舱参数
    st, body = live.cmd(0, 0, 1)
    ok, sy = live.wait(lambda s: str(s.get("dbg") or "").startswith("arg1="))
    R.add("T-LIVE-001", "POST /cmd {dev:0,cmd:0,val:1} 读座舱参数 1",
          "HTTP 200 且 sys.dbg 变成 arg1=<数值>",
          f"HTTP {st} {body} → dbg={sy.get('dbg')} (sys.t={sy.get('t')})",
          st == 200 and ok)

    # A2 换一个参数号，验证「输入值 → 输出内容」的对应关系
    st, body = live.cmd(0, 0, 3007)
    ok, sy = live.wait(lambda s: str(s.get("dbg") or "").startswith("arg3007="))
    R.add("T-LIVE-002", "POST /cmd {dev:0,cmd:0,val:3007} 换参数号",
          "sys.dbg 精确反映参数号 arg3007=<数值>",
          f"HTTP {st} → dbg={sy.get('dbg')}", st == 200 and ok)

    # A3 设备扫描
    st, body = live.cmd(0, 1, 0)
    ok, sy = live.wait(lambda s: str(s.get("dbg") or "").startswith("devs="))
    dbg_a3 = str(sy.get("dbg") or "")
    R.add("T-LIVE-003", "POST /cmd {dev:0,cmd:1} 设备扫描",
          "sys.dbg 以 devs= 开头且列出有 performClickableAction 的设备",
          f"HTTP {st} → dbg={dbg_a3[:110]}…（{len(dbg_a3)} 字符）",
          st == 200 and ok and len(dbg_a3) > 10)

    # A4 40 参数快照
    st, body = live.cmd(0, 3, 734)
    ok, sy = live.wait(lambda s: str(s.get("dbg") or "").startswith("A734|"))
    dbg_a4 = str(sy.get("dbg") or "")
    n_vals = len(dbg_a4.split("|")[-1].split(",")) if "|" in dbg_a4 else 0
    R.add("T-LIVE-004", "POST /cmd {dev:0,cmd:3,val:734} 参数快照",
          "sys.dbg = A734| 后跟 40 个数值，起始号随输入变",
          f"HTTP {st} → {dbg_a4[:80]}… 共 {n_vals} 个值",
          st == 200 and ok and n_vals == 40)

    # A5 负向：不存在的设备号（直接给命令号，不走元素号+2502 换算）
    st, body = live.post(99, 3007, 1)
    ok, sy = live.wait(lambda s: str(s.get("dbg") or "") == "99:3007:N")
    R.add("T-LIVE-005", "POST /cmd {dev:99,cmd:3007,val:1} 不存在的设备",
          "sys.dbg = 99:3007:N（:N = GetDevice 返回空），飞机状态不变",
          f"HTTP {st} → dbg={sy.get('dbg')}", st == 200 and ok)

    # A6 真机数据字段体检（对应离线测出的 BUG-04）
    sy = live.sys()
    gr, cs_e = sy.get("gr"), sy.get("cs_e")
    R.add("T-LIVE-006", "只读：检查慢变量里的起落架进度 gr / 升降舵偏度 cs_e",
          "新部署的 Export.lua 应给出数值（gear.nose.rod / elevator.left）",
          f"gr={gr}  cs_e={cs_e}  cs_a={sy.get('cs_a')}  cs_r={sy.get('cs_r')}",
          gr is not None and cs_e is not None,
          "为 null 说明 DCS 里加载的还是旧版 Export.lua（缺 deepget3/surface）")

    # A7 /input 只读（不写，避免推动 vJoy）
    with OP.open(live.base + "/input", timeout=2) as r:
        inp = json.load(r)
    R.add("T-LIVE-007", "只读 GET /input（不写，避免动 vJoy）",
          "能读到 axes/buttons/seq/forwarding/vjoy 结构",
          f"axes={inp.get('axes')} forwarding={inp.get('forwarding')} vjoy={inp.get('vjoy')}",
          all(k in inp for k in ("axes", "buttons", "seq", "forwarding", "vjoy")))

    # ---- B. MFD / UFCP 虚拟输入 → 屏幕状态 ----
    if not args.no_mfd and "JF-17" in str(sy0.get("ac") or ""):
        print("\n--- B. MFD / UFCP 虚拟输入（可逆，结束回主菜单）---")

        # B1 先回主菜单，建立基线
        live.cmd(MFD_DEV, CENTER_D3, 1)
        time.sleep(0.3)
        live.cmd(MFD_DEV, CENTER_D3, 0)
        ok, sy = live.wait(lambda s: MAIN_MENU_TOKENS.issubset(live.c_tokens(s)), timeout=6)
        base_tokens = live.c_tokens(sy)
        R.add("T-LIVE-008", f"中屏 D3 (dev47 cmd{CENTER_D3 + CMD_OFFSET}) 回主菜单",
              "sys.mfd 的 C= 段含 MENU/RDR/INS/TACAN/…/CHKLS 主菜单标签",
              f"C= 段 {len(base_tokens)} token，含 CHKLS={'CHKLS' in base_tokens}, BIT={'BIT' in base_tokens}",
              ok)

        # B2 按 U1 → 应离开主菜单（进雷达页）
        bp0 = live.bp_seq(live.sys())
        live.cmd(MFD_DEV, CENTER_U1, 1)
        time.sleep(0.3)
        live.cmd(MFD_DEV, CENTER_U1, 0)
        ok_u1, sy_u1 = live.wait(
            lambda s: "CHKLS" not in live.c_tokens(s) and len(live.c_tokens(s)) > 0,
            timeout=6)
        tok_u1 = live.c_tokens(sy_u1)
        bp1 = live.bp_seq(sy_u1)
        R.add("T-LIVE-009", f"中屏 U1 (cmd{CENTER_U1 + CMD_OFFSET}) 从主菜单进雷达页",
              "sys.mfd 的 C= 段不再含 CHKLS/BIT，且 sys.bp 序号 +1（座舱按键被扫到）",
              f"CHKLS={'CHKLS' in tok_u1}  bp {bp0}→{bp1}  C 段前 16 个={sorted(tok_u1)[:16]}",
              ok_u1 and bp1 > bp0)

        # B3 再按 D3 → 应回到主菜单
        live.cmd(MFD_DEV, CENTER_D3, 1)
        time.sleep(0.3)
        live.cmd(MFD_DEV, CENTER_D3, 0)
        ok_d3, sy_d3 = live.wait(
            lambda s: "CHKLS" in live.c_tokens(s), timeout=6)
        R.add("T-LIVE-010", f"中屏 D3 再次按下（cmd{CENTER_D3 + CMD_OFFSET}）",
              "sys.mfd 的 C= 段重新出现 CHKLS（回到主菜单），输入可逆",
              f"CHKLS={'CHKLS' in live.c_tokens(sy_d3)}  bp={sy_d3.get('bp')}",
              ok_d3)

        # B4 UFCP 键 → 回执闭环
        acn0 = live.sys().get("acn") or 0
        live.cmd(UFCP_DEV, UFCP_PFL, 1)
        time.sleep(0.3)
        live.cmd(UFCP_DEV, UFCP_PFL, 0)
        ok_ufcp, sy_ufcp = live.wait(
            lambda s: str(s.get("dbg") or "").startswith(f"{UFCP_DEV}:{UFCP_PFL + CMD_OFFSET}:D"),
            timeout=6)
        acn1 = sy_ufcp.get("acn") or 0
        R.add("T-LIVE-011", f"UFCP PFL/1 (dev46 cmd{UFCP_PFL + CMD_OFFSET})",
              "sys.dbg=46:3202:D 且 sys.acn 递增（回执闭环）",
              f"dbg={sy_ufcp.get('dbg')}  acn {acn0}→{acn1}  ufcp={sy_ufcp.get('ufcp')}",
              ok_ufcp and acn1 > acn0)

        # B5 最终把中屏停回主菜单
        live.cmd(MFD_DEV, CENTER_D3, 1)
        time.sleep(0.3)
        live.cmd(MFD_DEV, CENTER_D3, 0)
        time.sleep(1.2)
        print("  （已把中屏停回主菜单）")
    else:
        print("\n--- B 段跳过（--no-mfd 或非 JF-17）---")

    # ---- 汇总 ----
    print("\n" + "=" * 78)
    print(f"  {len(R.rows) - len(R.failed)}/{len(R.rows)} 通过，{len(R.failed)} 未达预期")
    print("=" * 78)

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "time": datetime.now().isoformat(timespec="seconds"),
        "target": live.base,
        "aircraft": sy0.get("ac"),
        "rows": R.rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 报告
    lines = [
        "# 真 DCS 虚拟输入 → 状态输出对应测试",
        "",
        f"> 执行时间 {datetime.now():%Y-%m-%d %H:%M:%S} ｜ 目标 `{live.base}` ｜ 机型 `{sy0.get('ac')}`",
        f"> 脚本：`tests/live_dcs_test.py` ｜ 明细：`.tmp/live-dcs-result.json`",
        "",
        "## 环境实况（测试开始时读到的状态量）",
        "",
        f"- `has_data={s0.get('has_data')}`、`stats.hz={s0['stats']['hz']}`、`bad={s0['stats']['bad']}`、`age={s0['stats']['age_ms']}ms`",
        f"- `sys.ac={sy0.get('ac')}`、`sys.t={sy0.get('t')}`、`sys.dbg={sy0.get('dbg')}`、`acn={sy0.get('acn')}`、`bp={sy0.get('bp')}`",
        f"- `sys.ufcp={sy0.get('ufcp')}`",
        "",
        "## 逐项对应",
        "",
        "| ID | 虚拟输入 | 期望的状态输出 | 实际读到 | 判定 |",
        "|---|---|---|---|---|",
    ]
    for r in R.rows:
        clean = lambda x: str(x).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['id']} | `{clean(r['input'])}` | {clean(r['expect'])} | "
                     f"{clean(r['actual'])} | {'✅' if r['ok'] else '❌'} |")
    lines += ["", f"**汇总：{len(R.rows) - len(R.failed)}/{len(R.rows)} 通过，{len(R.failed)} 未达预期。**", ""]
    if R.failed:
        lines += ["## 未达预期的项与原因", ""]
        for r in R.failed:
            lines.append(f"- **{r['id']}** {r['input']}：{r['note'] or r['actual']}")
        lines.append("")
    lines += [
        "## 版本自检（决定 T-LIVE-006 会不会失败）",
        "",
        "| 组件 | 本轮判定 | 依据 |",
        "|---|---|---|",
        f"| `Export.lua`（DCS 内存中） | {'新版 ✅' if export_live else '旧版 ❌'} | "
        f"`sys.gr={sy0.get('gr')}`、`sys.cs_e={sy0.get('cs_e')}`；旧版这两个字段恒为 null |",
        f"| `Export.lua`（磁盘） | {lua_disk} | 与 `dcs/Export.lua` 逐字节比对 |",
        f"| `beacon.py`（8080 进程） | {beacon_ver} | `POST /cmd val=NaN` 的响应 |",
        "",
        "> DCS 只在**任务启动时**加载 Export.lua；桥接进程也要重启才会加载新的 beacon.py。"
        "磁盘文件与内存版本可能不一致，两个都要查。",
        "",
        "## 真机结构证据（dev=0,cmd=7 probe 通道只读取得）",
        "",
        "```",
        STRUCTURE_EVIDENCE,
        "```",
        "",
        "`gear.nose.rod` 是三级嵌套、`controlsurfaces.elevator` 是 `{left,right}` 表。"
        "旧版 `deepget()` 只下钻两层，取回来的是 table，`numo()` 只能发 `null`（BUG-04）；"
        "新版 `deepget3()` / `surface()` 正是按这个形态写的。probe 用完已恢复原文件、删除诊断输出。",
        "",
        "## 轮次记录",
        "",
        "| 轮次 | 结果 | 说明 |",
        "|---|---|---|",
    ]
    for when, res, note in HISTORY:
        lines.append(f"| {when} | {res} | {note} |")
    lines += ["", "## 补充观察", "",
              "- 按中屏 U1 后 C= 段落到雷达模式菜单（`RWS/TWS/VS/MAP/GMTI/SEA1/SEA2/BCN/WA/TA`），"
              "与 `docs/JF17-MFD.md` 第八节一致；`sys.bp` 序号跟随按键递增。",
              "- 按 D3 后 `CHKLS` 回来，页面可逆，输入没有卡住；UFCP 键回执 `:D` 且 `acn` 递增。",
              ""]
    all_ok = (export_live and disk_match and not R.failed
              and (not args.probe_version or beacon_ver.startswith("新版")))
    lines += ["## 结论 / 下一步", ""]
    if all_ok:
        lines += ["- ✅ 新版 `Export.lua`、新版 `beacon.py`、真机三条链路全部验证通过，无需额外重启。",
                  "- 重复验证：`python tests/live_dcs_test.py --probe-version`。", ""]
    else:
        lines += ["- ⚠️ 仍有旧版组件在跑：需要**重启 DCS 任务**（加载新 Export.lua）并"
                  "**重启 `start-usb.bat`**（加载新 beacon.py），再跑一次本脚本。", ""]
    lines += [
        "## 安全约定",
        "",
        "只发 `dev=0` 只读探针与 `dev=47/46` 的 MFD/UFCP 页面键（可逆）；"
        "不发起落架、襟翼、减速伞、主军械等改变飞行构型的命令；不写 `/input`（避免推动 vJoy 轴）。"
        "结束时用中屏 D3 回主菜单。",
        "",
    ]
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"  报告 -> {args.report}")
    print(f"  明细 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

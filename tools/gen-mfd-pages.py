"""把 DCS 的 MFD 页面数据生成 panel.html 里用的 JS 常量。

数据来自 `tools/dump-mfd-pages.py`（解析 `Cockpit/Scripts/MFCD/Indicator/*.lua`），
本脚本负责补上三样代码里没有的东西：

1. 中文页名（`TITLES`）
2. 一句话说明（`DESC`），只给常用页写
3. **页面跳转表（`TRANS`）** —— 按了这个键会去哪个页面

跳转表为什么要手写：页面切换发生在编译过的设备 DLL 里，Lua 侧只看得到
「这个键上画了什么字」，看不到「按了会跳到哪」。好在键名本身已经把跳转关系
说清楚了（`UP_U1_RDR_Mode` 就是雷达页按 U1 出来的模式菜单），照着文件名就能填。

用法：python tools/gen-mfd-pages.py        # 直接改写 tools/panel.html 里标记之间的块
"""
import json
import re
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "tools" / "panel.html"

_spec = importlib.util.spec_from_file_location("dump", Path(__file__).with_name("dump-mfd-pages.py"))
_dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dump)

TITLES = {
    "UP_MainMenu": "主菜单",
    "UP_U1_RDR_AA": "雷达·空对空",
    "UP_U1_RDR_AA_CNTL": "雷达·控制菜单",
    "UP_U1_RDR_Mode": "雷达·模式选择",
    "UP_U1_RDR_AG": "雷达·空对地",
    "UP_U1_RDR_AG_CNTL": "雷达·对地控制菜单",
    "UP_U2_INS": "惯导 INS",
    "UP_U3_TACAN": "塔康 TACAN",
    "UP_U3_TACAN_Prog": "塔康·程序",
    "UP_U4_APR": "应答机 APR",
    "UP_U5_POD": "吊舱 POD",
    "UP_L1_HSD": "水平状态 HSD",
    "UP_L2_EFIS": "电子仪表 EFIS",
    "UP_L3_CLINK": "数据链 CLINK",
    "UP_L3_CLINK_List": "数据链·列表",
    "UP_L4_DATA": "数据 DATA",
    "UP_R1_SMS_AA": "外挂·空对空",
    "UP_R1_SMS_AA_Base": "外挂·空对空·基础",
    "UP_R1_SMS_AA_Wpn": "外挂·空对空·选弹",
    "UP_R1_SMS_AA_Limiter": "外挂·空对空·机炮限数",
    "UP_R1_SMS_AA_Gunsight": "外挂·空对空·准心",
    "UP_R1_SMS_AG": "外挂·空对地",
    "UP_R1_SMS_AG_Mode": "外挂·对地·投放模式",
    "UP_R1_SMS_AG_Fuze": "外挂·对地·引信",
    "UP_R1_SMS_AG_Qty": "外挂·对地·数量",
    "UP_R1_SMS_AG_Intv": "外挂·对地·间隔",
    "UP_R1_SMS_AG_Profile": "外挂·对地·程序",
    "UP_R1_SMS_AG_Wpn": "外挂·对地·选弹",
    "UP_R1_SMS_Load": "外挂·挂载",
    "UP_R1_SMS_Load_Type": "挂载·类型",
    "UP_R1_SMS_Load_Wpn": "挂载·选弹",
    "UP_R1_SMS_Prog": "外挂·程序",
    "UP_R1_SMS_Jet": "外挂·投放",
    "UP_R2_CMBT": "战斗 CMBT",
    "UP_R3_BIT": "自检 BIT",
    "UP_R4_CHKLS": "检查单 CHKLS",
    "UP_R5_PFL": "PFL",
    "UP_DATA_RLS": "DATA·挂点",
    "UP_DATA_NAV": "DATA·导航",
    "UP_DATA_FCS": "DATA·飞控",
    "UP_DATA_ENG": "DATA·发动机",
    "UP_DATA_FUEL": "DATA·燃油",
    "UP_DATA_DTC": "DATA·数据卡",
    "UP_DATA_DST": "DATA·目的地",
    "UP_DATA_AS": "DATA·大气",
    "UP_DATA_SPCHK": "DATA·飞控自检",
    "UP_DATA_DEdit": "DATA·数字输入",
    "UP_EDIT": "数字键盘",
    "UP_NOAUX": "无信号",
    "UP_OFF": "断电",
    "DOWN_MainMenu": "下半区·菜单",
    "DOWN_SMS": "下半区·外挂",
    "DOWN_CLINK": "下半区·数据链",
    "DOWN_EPI1": "下半区·应急程序 1",
    "DOWN_EPI2": "下半区·应急程序 2",
    "DOWN_AFINFO": "下半区·机场信息",
    "DOWN_AG_DATA": "下半区·对地数据",
    "DOWN_BLANK": "下半区·空白",
}

DESC = {
    "UP_MainMenu": "所有画面都从这里进。D3 随时回这一页。",
    "UP_U1_RDR_AA": "左列是搜索参数：方位角 60 / 天线稳定 NOR / 扫描行数 4BR。U1 进模式菜单，U5 进控制菜单。",
    "UP_U1_RDR_Mode": "雷达模式菜单。左列 RWS/TWS/VS/MAP/GMTI，右列 SEA1/SEA2/BCN/WA/TA。",
    "UP_U1_RDR_AA_CNTL": "雷达控制菜单。U5 再按一次退回雷达页。",
    "UP_L4_DATA": "DATA 主页。左列 挂点/导航/大气/燃油，右列 目的地/飞控/发动机/数据卡。",
    "UP_R1_SMS_AA": "空对空外挂。L3 机炮准心、L4 限数、U5 进挂载页。",
    "UP_R2_CMBT": "战斗页：干扰弹与投放程序。",
}

# 代码里没有静态 value、但知道它是什么的键（屏幕上是运行时画的字）
OVERRIDE = {
    # 雷达页右列：显示的是当前值，旁边的键才是加减（2026-11-13 实测）
    # CNTL 菜单开着时，右列变成这三个（2026-11-13 实测：R2 翻 L/H、
    # R3 是 HST——TWS 下按了没反应、R5 是 DCLT 按了水平线消失）。
    # R5 在代码里同时挂着 PRF 读数（rdr_aa_prf_setting），两者关系未验证。
    "UP_U1_RDR_AA": {"U1": "模式", "R1": "距离+", "R2": "L/H", "R3": "HST", "R5": "DCLT"},
    "UP_U1_RDR_AG": {"U1": "模式", "R1": "距离+", "R2": "距离-", "R5": "PRF"},
    # 模式菜单在代码里只画数字 1..10，名字是设备运行时填的。
    # 2026-11-13 截图实测出来的对应关系（见 docs/JF17-MFD.md 第八节）。
    "UP_U1_RDR_Mode": {
        "L1": "RWS", "L2": "TWS", "L3": "VS", "L4": "MAP", "L5": "GMTI",
        "R1": "SEA1", "R2": "SEA2", "R3": "BCN", "R4": "WA", "R5": "TA",
    },
}

# 页面跳转。没写的键 = 原地不动（改参数、循环档位那种）。
TRANS = {
    "UP_MainMenu": {
        "U1": "UP_U1_RDR_AA", "U2": "UP_U2_INS", "U3": "UP_U3_TACAN",
        "U4": "UP_U4_APR", "U5": "UP_U5_POD",
        "L1": "UP_L1_HSD", "L2": "UP_L2_EFIS", "L3": "UP_L3_CLINK", "L4": "UP_L4_DATA",
        "R1": "UP_R1_SMS_AA", "R2": "UP_R2_CMBT", "R3": "UP_R3_BIT",
        "R4": "UP_R4_CHKLS", "R5": "UP_R5_PFL",
    },
    "UP_U1_RDR_AA": {"U1": "UP_U1_RDR_Mode", "U5": "UP_U1_RDR_AA_CNTL", "U2": "UP_U1_RDR_AA_CNTL"},
    "UP_U1_RDR_AG": {"U1": "UP_U1_RDR_Mode", "U5": "UP_U1_RDR_AG_CNTL", "U2": "UP_U1_RDR_AG_CNTL"},
    "UP_U1_RDR_Mode": {
        "L1": "UP_U1_RDR_AA", "L2": "UP_U1_RDR_AA", "L3": "UP_U1_RDR_AA",
        "L4": "UP_U1_RDR_AA", "L5": "UP_U1_RDR_AA",
        "R1": "UP_U1_RDR_AA", "R2": "UP_U1_RDR_AA", "R3": "UP_U1_RDR_AA",
        "R4": "UP_U1_RDR_AA", "R5": "UP_U1_RDR_AA",
    },
    "UP_U1_RDR_AA_CNTL": {"U5": "UP_U1_RDR_AA"},
    "UP_U1_RDR_AG_CNTL": {"U5": "UP_U1_RDR_AG"},
    "UP_L4_DATA": {
        "L1": "UP_DATA_RLS", "L2": "UP_DATA_NAV", "L3": "UP_DATA_AS", "L4": "UP_DATA_FUEL",
        "R1": "UP_DATA_DST", "R2": "UP_DATA_FCS", "R3": "UP_DATA_ENG", "R4": "UP_DATA_DTC",
    },
    "UP_DATA_FCS": {"U5": "UP_DATA_SPCHK"},
    "UP_DATA_SPCHK": {"U5": "UP_DATA_FCS"},
    "UP_U2_INS": {"U1": "UP_U2_INS"},
    "UP_U3_TACAN": {"U1": "UP_U3_TACAN"},
    "UP_L1_HSD": {"U1": "UP_L1_HSD"},
    "UP_L2_EFIS": {"U1": "UP_L2_EFIS"},
    "UP_L3_CLINK": {"U1": "UP_L3_CLINK"},
    "UP_R1_SMS_AA": {"U5": "UP_R1_SMS_Load", "R2": "UP_R1_SMS_AA_Wpn", "R2x": "UP_R1_SMS_AA_Wpn"},
    "UP_R1_SMS_AA_Base": {"U5": "UP_R1_SMS_Load"},
    "UP_R1_SMS_AG": {"U5": "UP_R1_SMS_Load", "L1": "UP_R1_SMS_AG_Mode"},
    "UP_R1_SMS_Load": {"L2": "UP_R1_SMS_Load_Type", "U1": "UP_R1_SMS_Load"},
}

ORDER = ["UP_MainMenu"] + sorted(k for k in TITLES if k != "UP_MainMenu")


NAME_RE = re.compile(r'name\s*=\s*"([a-z][a-z0-9_]*)"')


def elem_names(path):
    """页面里 CreateElement 的 name 字段 —— 这就是该页的元素名指纹。"""
    text = _dump.strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    return sorted(set(NAME_RE.findall(text)))


def main():
    pages = {}
    names = {}
    for f in sorted(_dump.IND.glob("*.lua")):
        d = _dump.parse(f)
        if d:
            pages[f.stem] = d
        nm = elem_names(f)
        if nm:
            names[f.stem] = nm

    # *_Base.lua 是子页 dofile 进来的基础层，不是独立画面：把它的键并进子页，
    # 自己不进下拉框（否则下拉里会出现一堆永远显示不出来的"页"）。
    for pid in list(pages):
        if pid.endswith("_Base"):
            continue
        base = pages.get(pid + "_Base")
        if names.get(pid + "_Base"):
            names[pid] = sorted(set(names.get(pid, [])) | set(names[pid + "_Base"]))
        # 雷达四个子页共用 UP_U1_RDR_Base.lua（U5=CNTL 就写在那一层）
        if pid.startswith("UP_U1_RDR_") and pages.get("UP_U1_RDR_Base"):
            base = {**pages["UP_U1_RDR_Base"], **(base or {})}
        if base:
            pages[pid] = {**base, **pages[pid]}
    for pid in [k for k in pages if k.endswith("_Base")]:
        del pages[pid]
    # FULL_BASE 是所有页共享的底图（带 D2/D3/D4 那几个通用元素），不是一页画面。
    # 留着会让识别打分时「谁都能匹配上一堆元素」，必须踢掉。
    pages.pop("FULL_BASE", None)
    names.pop("FULL_BASE", None)
    # HSD 的显示内容分散在 _NAV/_SA/_TGT 三个子页里，但物理上就是同一块屏的
    # 不同模式，识别时应该合起来看，否则光看两三个元素名认不出来。
    for pid, family in {"UP_L1_HSD": ("UP_L1_HSD_NAV", "UP_L1_HSD_SA", "UP_L1_HSD_TGT")}.items():
        acc = set(names.get(pid, []))
        for sub in family:
            acc |= set(names.get(sub, []))
        if acc:
            names[pid] = sorted(acc)

    # osb_txt 是每个页面都用的通用键标签元素，不带页面信息，剔除
    for pid in list(names):
        names[pid] = [n for n in names[pid] if not n.startswith("osb_txt")]

    for pid, ov in OVERRIDE.items():
        if pid in pages:
            pages[pid] = {**pages[pid], **ov}

    # 中文按页面顺序排，方便在 iPad 的下拉里找
    ordered = [k for k in ORDER if k in pages] + [k for k in pages if k not in ORDER]
    data = {}
    out = []
    for pid in ordered:
        o = {"t": TITLES.get(pid, pid), "k": pages[pid]}
        if names.get(pid):
            o["e"] = names[pid]
        if pid in DESC:
            o["d"] = DESC[pid]
        if pid in TRANS:
            o["n"] = {k: v for k, v in TRANS[pid].items() if not k.endswith("x") and v != pid}
        data[pid] = o
        out.append(f'  {json.dumps(pid)}:' + json.dumps(o, ensure_ascii=False, separators=(",", ":")))

    block = ("// MFDPAGES:BEGIN —— 由 tools/gen-mfd-pages.py 生成，别手改\n"
             "const MFD_PAGES = {\n" + ",\n".join(out) + "\n};\n"
             "// MFDPAGES:END")

    # 同一份数据也给读屏工具用（tools/mfd-read.py 靠它把 OCR 结果匹配成页面）
    (ROOT / "tools" / "mfd-pages.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")

    html = PANEL.read_text(encoding="utf-8")
    new, n = re.subn(r"// MFDPAGES:BEGIN.*?// MFDPAGES:END", lambda _: block, html, flags=re.S)
    if n != 1:
        raise SystemExit(f"panel.html 里找不到 MFDPAGES 标记（匹配 {n} 次）")
    PANEL.write_text(new, encoding="utf-8")
    print(f"写入 {len(pages)} 个页面 -> {PANEL.name}")


if __name__ == "__main__":
    main()

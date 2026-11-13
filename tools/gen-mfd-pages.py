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
    "DOWN_FUEL": "下半区·燃油",
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
    # 挂载页没有可识别的元素名（全是动态文本），面板认不出画面，
    # 只能靠按键跳转或下拉框手动选 —— 说明里写清楚键位分布。
    "UP_R1_SMS_Load": "挂载管理：U1-U5 选挂点 2-6，L2 进挂载类型，D1 清除 / D2 复制 / D4 回外挂页。本页面板认不出，选一下下拉框即可。",
    "UP_R1_SMS_AA_Wpn": "选弹页：右列列出可用武器，选中的挂点会高亮。",
    # 以下几个页面以屏幕显示文本为主，周边键只有 U1（标题键），内容全是无元素名的
    # 动态文本 → 键位稀是页面本身的形状，面板也无法从画面自动识别，得靠下拉框手动标。
    "UP_U2_INS": "惯导状态页：显示 INS OFF / 对准（ALIGN）进度与剩余时间、当前经纬度。周边键只有 U1，纯状态显示。",
    "UP_U3_TACAN": "塔康主页（手册 2.5.1）：显示工作模式/频道/磁航线/编码 X-Y/塔康高度/磁差。键改旁边的值：L2 模式(A/A-S、A/A-B、A/G、RCV)、R2 频道、L3 航线、R3 波段、L4 站高、R4 磁差；U1 进通道程序页。也能从雷达模式菜单 R5(TA) 进来。",
    "UP_U4_APR": "进近页（手册 1.12.6）：显示 ILS 波道/跑道号、下滑角、最低高度、机场坐标。右显对应 10 个着陆机场（目标 50-59），周边键只能改目标 59 的数据；APR 模式按 U5 可人工切换真北/磁北。",
    "UP_U5_POD": "吊舱选择页：R1 进 WMD7 侦察吊舱、L1 进 TVIR、R4 进 MIL，画面交给对应吊舱。",
    "UP_L3_CLINK": "数据链状态页：ID / NET 开关 / MODE（SLAVE）/ 通道号。U1 进计划列表。",
    "UP_U3_TACAN_Prog": "塔康设置页：L1-5/R1-5 选 TCN01-TCN10 号预存通道，改完后 U1 回塔康主页。页面无元素名，面板认不出，手动选下拉框。",
    "UP_L3_CLINK_List": "数据链计划列表（各_group 的规划清单）。U1 RTN 回数据链主页。",
    # 下半区页面（LR6-8 键控制，与上半区互不干扰）
    "DOWN_MainMenu": "下半区小菜单：R6/R7 应急程序，L6 机场信息，L7 外挂摘要。R8 返回。",
    "DOWN_SMS": "外挂摘要：各挂点当前挂的武器。上半区雷达页的下半区固定显示它。",
    "DOWN_AFINFO": "起飞/降落机场信息。R6 下一页，R7 上一页，R8 返回。",
    "DOWN_EPI1": "应急程序检查单第 1 页。L6 回下半区菜单。",
    "DOWN_EPI2": "应急程序检查单第 2 页。L6 回下半区菜单。",
    "DOWN_CLINK": "数据链状态。R8 返回。",
    "DOWN_FUEL": "燃油/发动机监控（油量表、TOTAL FEED）。纯图形显示，面板认不出，可从下拉框手动选。",
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
    # 塔康主页：显示文本挂在键旁边，按旁边的键改值（手册 2.5.1 图注 + 脚本坐标，
    # 交互模式和雷达页 60/40 相同——推断，待实测确认）
    "UP_U3_TACAN": {
        "L2": "模式", "R2": "频道", "L3": "航线", "R3": "波段", "L4": "站高", "R4": "磁差",
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
        # 选模式后回雷达页；R5=TA 进塔康（手册 2.5.1：塔康设置可从雷达菜单进）
        "L1": "UP_U1_RDR_AA", "L2": "UP_U1_RDR_AA", "L3": "UP_U1_RDR_AA",
        "L4": "UP_U1_RDR_AA", "L5": "UP_U1_RDR_AA",
        "R1": "UP_U1_RDR_AA", "R2": "UP_U1_RDR_AA", "R3": "UP_U1_RDR_AA",
        "R4": "UP_U1_RDR_AA", "R5": "UP_U3_TACAN",
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
    # U1 是标题键，实测里按下会在主/设置子页之间切换（和雷达页 CNTL 同款交互）
    "UP_U3_TACAN": {"U1": "UP_U3_TACAN_Prog"},
    "UP_U3_TACAN_Prog": {"U1": "UP_U3_TACAN"},
    "UP_L1_HSD": {"U1": "UP_L1_HSD"},
    "UP_L2_EFIS": {"U1": "UP_L2_EFIS"},
    "UP_L3_CLINK": {"U1": "UP_L3_CLINK_List"},
    "UP_L3_CLINK_List": {"U1": "UP_L3_CLINK"},
    "UP_R1_SMS_AA": {"U5": "UP_R1_SMS_Load", "R2": "UP_R1_SMS_AA_Wpn", "R2x": "UP_R1_SMS_AA_Wpn"},
    "UP_R1_SMS_AA_Base": {"U5": "UP_R1_SMS_Load"},
    "UP_R1_SMS_AG": {"U5": "UP_R1_SMS_Load", "L1": "UP_R1_SMS_AG_Mode"},
    "UP_R1_SMS_Load": {"L2": "UP_R1_SMS_Load_Type", "U1": "UP_R1_SMS_Load"},
}

ORDER = ["UP_MainMenu"] + sorted(k for k in TITLES if k != "UP_MainMenu")


# 单双引号都要认：脚本里两种写法混用（current_wpt.name = 'rdr_aa_current_wpt'）
NAME_RE = re.compile(r"name\s*=\s*[\"']([a-z][a-z0-9_]*)[\"']")


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
        # 雷达四个子页共用 UP_U1_RDR_Base.lua（rdr_frame_box_clip 等就写在那层）
        if pid.startswith("UP_U1_RDR_") and names.get("UP_U1_RDR_Base"):
            names[pid] = sorted(set(names.get(pid, [])) | set(names["UP_U1_RDR_Base"]))
        if names.get(pid + "_Base"):
            names[pid] = sorted(set(names.get(pid, [])) | set(names[pid + "_Base"]))
        # 雷达四个子页共用 UP_U1_RDR_Base.lua（U5=CNTL 就写在那一层）
        if pid.startswith("UP_U1_RDR_") and pages.get("UP_U1_RDR_Base"):
            base = {**pages["UP_U1_RDR_Base"], **(base or {})}
        if base:
            pages[pid] = {**base, **pages[pid]}
    for pid in [k for k in pages if k.endswith("_Base")]:
        del pages[pid]

    # 元素名按脚本 dofile 引用链传递合并：
    #   UP_R1_SMS_AA -> AA_Base -> SMS_Base（sms_pilon 在最底层，全家引用它）
    #   UP_U1_RDR_AA -> AA_Base -> Contact（rdr_aa_current_wpt 在 Contact 层）
    # 只认没被注释的 dofile（SMS_AA.lua 里有 --dofile 的旧引用，不能算）。
    DOFILE_RE = re.compile(r'dofile\s*\(.*?"([A-Za-z0-9_./-]+\.lua)"')
    includes = {}
    for f in sorted(_dump.IND.glob("*.lua")):
        text = _dump.strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        includes[f.stem] = {m.group(1).rsplit("/", 1)[-1][:-4] for m in DOFILE_RE.finditer(text)}

    def inc_closure(stem):
        seen, stack = set(), list(includes.get(stem, ()))
        while stack:
            d = stack.pop()
            if d in seen or d not in includes:
                continue
            seen.add(d)
            stack.extend(includes[d])
        return seen

    for pid in list(names):
        acc = set(names[pid])
        for d in inc_closure(pid):
            acc |= set(names.get(d, ()))
        if len(acc) > len(names[pid]):
            names[pid] = sorted(acc)
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

    # 燃油/发动机监控是纯图形下半区页面（LR6-8 里 R8 能回到它），没有可解析的
    # 脚本内容，但不进数据的话下拉框里就没有、用户也没法手动标
    pages.setdefault("DOWN_FUEL", {})

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

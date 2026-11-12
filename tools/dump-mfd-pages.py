"""从 DCS 的 JF-17 MFD 页面脚本里抽出「每个页面、每个周边键上写的是什么」。

数据源：D:\\DCS World\\Mods\\aircraft\\JF-17\\Cockpit\\Scripts\\MFCD\\Indicator\\*.lua
这些文件就是 MFD 的绘制代码，每个 OSB 标签都是一条 {value="XXX", cx=..., cy=...}，
坐标常量直接对应物理键（UD1..UD5 = 上排，L/R_HORI_X + LRn_Y = 左右列，D_Y = 下排）。

用法：python tools/dump-mfd-pages.py [--json]
"""
import json
import re
import sys
from pathlib import Path

MFCD = Path(r"D:/DCS World/Mods/aircraft/JF-17/Cockpit/Scripts/MFCD")
IND = MFCD / "Indicator"

# 坐标常量 -> 键名。按符号名匹配，不按数值：LR6_Y 和 LR2_Y 数值相同，
# 只能靠用的是哪个常量名来区分 L6 / L2。
CX = {
    "MFCD_FONT_UD1_X": "U1", "MFCD_FONT_UD2_X": "U2", "MFCD_FONT_UD3_X": "U3",
    "MFCD_FONT_UD4_X": "U4", "MFCD_FONT_UD5_X": "U5",
}
SIDE = {"MFCD_FONT_L_HORI_X": "L", "MFCD_FONT_R_HORI_X": "R"}
ROW = {f"MFCD_FONT_LR{i}_Y": i for i in range(1, 9)}

REC = re.compile(r"\{[^{}]*\}", re.S)


def spans(text):
    """所有花括号配对的区间 (起, 止)，用于把 value 归到它所在的记录里。

    不能用正则直接匹配 {…}：记录里套着 ctrls = {{...}}，一遇到嵌套就断。
    """
    out, stack = [], []
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            out.append((stack.pop(), i + 1))
    return out


def key_of(cx, cy):
    if cx in CX and cy in ("MFCD_FONT_U_Y",):
        return CX[cx]
    if cx in CX and cy in ("MFCD_FONT_D_Y",):
        return "D" + CX[cx][1]
    if cx in SIDE and cy in ROW:
        return SIDE[cx] + str(ROW[cy])
    return None


def strip_comments(text):
    """去掉 Lua 的块注释和行注释。

    必须做：雷达页里有 --[[ {cx=…, value="DGFT"} ]] 这种被注释掉的旧代码，
    不过滤就会把「已经废弃的标签」当成现状（L1 就从 BIND 被读成了 DGFT）。
    """
    text = re.sub(r"--\[\[.*?\]\]", "", text, flags=re.S)
    text = re.sub(r"--\[=*\[.*?\]=*\]", "", text, flags=re.S)
    return re.sub(r"--[^\n]*", "", text)


def parse(path):
    """返回 {键名: 标签}，按文件里出现顺序。"""
    out = {}
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    sp = sorted(spans(text), key=lambda s: s[1] - s[0])   # 由小到大，取最内层
    for vm in re.finditer(r'value\s*=\s*"([^"]*)"', text):
        p = vm.start()
        body = None
        for s, e in sp:
            if s < p < e:
                body = text[s:e]
                break
        if not body:
            continue
        cm = re.search(r"cx\s*=\s*([A-Za-z0-9_]+)", body)
        ym = re.search(r"cy\s*=\s*([A-Za-z0-9_]+)", body)
        if cm and ym:
            cx, cy = cm.group(1), ym.group(1)
        else:
            pm = re.search(r"init_pos\s*=\s*\{\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)", body)
            if not pm:
                continue
            cx, cy = pm.group(1), pm.group(2)
        k = key_of(cx, cy)
        if k and k not in out:
            out[k] = vm.group(1)
    return out


def main():
    rows = {}
    for f in sorted(IND.glob("*.lua")):
        d = parse(f)
        if d:
            rows[f.stem] = d
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    for page, d in rows.items():
        keys = " ".join(f"{k}={v}" for k, v in sorted(
            d.items(), key=lambda kv: (kv[0][0] not in "ULRD", kv[0])))
        print(f"{page:26s} {keys}")


if __name__ == "__main__":
    main()

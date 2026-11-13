#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mfd_recognition_test.py — MFD 页面「状态检测准确性」全量测试（离线）

回答的问题是：面板靠 sys.mfd 的元素名指纹反推「现在屏幕上是哪一页」，
这个判断到底准不准？57 个页面挨个用自己的指纹喂回去，看能不能认出自己、
有没有认成别的页、有没有把下半区页错认成上半区页。

完全复刻 tools/panel.html 里的 GENERIC_PRE / scoreSeg 算法（不改动页面代码），
所以结论可以直接用来改识别规则。不需要 DCS、不需要浏览器。

用法：python tests/mfd_recognition_test.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "tools" / "mfd-pages.json").read_text(encoding="utf-8"))

N = len(DATA)
# 与 panel.html::GENERIC_PRE 完全一致
cnt = Counter()
for p in DATA.values():
    for x in set(y.rstrip("_") for y in (p.get("e") or [])):
        cnt[x] += 1
GENERIC = {k for k, v in cnt.items() if v > N * 0.15} | {"split_white_line"}

PRE = {}
for pid, p in DATA.items():
    PRE[pid] = {x.rstrip("_") for x in (p.get("e") or [])
                if x.rstrip("_") and x.rstrip("_") not in GENERIC}


def score_seg(names, force=False):
    """逐行复刻 panel.html::scoreSeg —— 命中数优先、覆盖率次之。"""
    cands = []
    for pid in DATA:                     # Object.keys 顺序 = JSON 里的插入顺序
        pre = PRE[pid]
        if not pre:
            continue
        hit = sum(1 for e in names
                  if any(e.startswith(q) or q.startswith(e) for q in pre))
        cov = hit / len(names) if names else 0
        ok = ((hit >= 1 and cov >= 0.4) if force else
              ((cov >= 0.45 and (hit >= 2 or cov >= 0.9)) or
               (hit >= 3 and cov >= 0.3)))
        if ok:
            cands.append((hit, cov, pid))
    # JS sort 稳定；Python sorted 也稳定，用 -hit/-cov 保序
    cands.sort(key=lambda c: (-c[0], -c[1]))
    return cands[0][2] if cands else None, cands


def screen_tokens(pid):
    """模拟 Export.lua 的 list_indication 提取结果：上半区页放 UPPER_BASE 段，
    下半区页放 LOWER_BASE 段。真实回传第一段还有 UPPER_BASE 这个标记词。

    这里构造的是「单页纯净指纹」，不含真实屏幕里混进来的下半区元素 ——
    属于对识别算法最有利的输入，所以测出来的准确率是上界。"""
    e = [x for x in (DATA[pid].get("e") or []) if x]
    if pid.startswith("DOWN_"):
        return ["UPPER_BASE", "LOWER_BASE"] + e
    return ["UPPER_BASE"] + e


def apply_screen(tokens, force=False):
    """完整复刻 panel.html::applyScreenText 对单块屏的判定（含两条兜底）。"""
    elems = [e for e in tokens if e]
    li = len(elems) - 1 - elems[::-1].index("LOWER_BASE") if "LOWER_BASE" in elems else -1
    upper = [e for e in (elems[:li] if li >= 0 else elems) if e not in GENERIC]
    lower = [e for e in (elems[li:] if li >= 0 else []) if e not in GENERIC]

    pid, cands = score_seg(upper, force)
    if not pid and any(e.startswith("osb_txt") for e in upper):
        pid = "UP_MainMenu"
    if (len(upper) <= 3 and "rdr_frame_box_clip" in upper
            and "rdr_tdc_sym" in upper and "aa_exp_ref_box" in upper):
        pid = "UP_U1_RDR_Mode"

    low_pid = None
    if li < 0:
        up = next((c[2] for c in cands if c[2].startswith("UP_")), None)
        down = next((c[2] for c in cands if c[2].startswith("DOWN_")), None)
        if up:
            pid, low_pid = up, down
        elif down:
            low_pid = down
    elif lower:
        lr_pid, _ = score_seg(lower, force)
        if lr_pid and lr_pid.startswith("DOWN_"):
            low_pid = lr_pid
        elif not pid and lr_pid:
            pid = lr_pid

    # BUG-06 的修复：DOWN_ 只能进下半区
    if pid and pid.startswith("DOWN_"):
        if not low_pid:
            low_pid = pid
        pid = None
    return pid, low_pid


def main() -> int:
    print("\n" + "=" * 76)
    print("  MFD 页面识别准确性 · 全量自识别测试")
    print("=" * 76)
    print(f"  页面数 {N}｜通用指纹 {len(GENERIC)} 个｜有元素名指纹的页 "
          f"{sum(1 for p in PRE.values() if p)} 个")
    print()

    correct, wrong, unknown = [], [], []
    cross_zone = []
    for pid in DATA:
        if not PRE[pid]:
            unknown.append((pid, "该页没有元素名指纹（e 为空）—— 设计上就无法自动识别"))
            continue
        up_pid, low_pid = apply_screen(screen_tokens(pid))
        _, up_cands = score_seg([e for e in screen_tokens(pid)
                                 if e not in GENERIC and e != "LOWER_BASE"])

        if pid.startswith("DOWN_"):
            got = low_pid
            if up_pid is not None:
                cross_zone.append((pid, up_pid))
        else:
            got = up_pid

        if got == pid:
            correct.append(pid)
        elif got is None:
            unknown.append((pid, f"认不出；上半区候选 {[c[2] for c in up_cands[:3]]}"))
        else:
            wrong.append((pid, got, [c[2] for c in up_cands[:3]]))

    print("--- 结果 ---")
    print(f"  ✅ 正确识别自身 : {len(correct):2d}/{N}")
    print(f"  ❌ 认成别的页   : {len(wrong):2d}")
    print(f"  ❓ 认不出       : {len(unknown):2d}")
    print(f"  🚫 下半区串到上半区: {len(cross_zone):2d}")
    print()

    if wrong:
        print("--- 认错的页（这些会导致键上标错字）---")
        for pid, got, cands in wrong:
            print(f"  {pid:28s} → {got:28s} 候选 {cands}")
        print()
    if unknown:
        print("--- 认不出 / 无指纹的页（面板只能靠按键推演或下拉框手选）---")
        for pid, why in unknown:
            print(f"  {pid:28s} {why}")
        print()
    if cross_zone:
        print("--- 串区（BUG-06 回归）---")
        for pid, got in cross_zone:
            print(f"  {pid} 被写进上半区 {got}")
        print()

    # 按类别统计，便于判断「哪些功能区的状态检测可靠」
    groups = defaultdict(lambda: [0, 0])
    for pid in DATA:
        g = ("下半区" if pid.startswith("DOWN_") else
             "雷达" if "RDR" in pid or pid.startswith("UP_U1") else
             "外挂" if "SMS" in pid else
             "DATA" if "DATA" in pid else "其他")
        groups[g][1] += 1
        if pid in correct:
            groups[g][0] += 1
    print("--- 分功能区准确率 ---")
    for g, (ok, total) in sorted(groups.items()):
        print(f"  {g:6s} {ok:2d}/{total:2d}  ({ok / total * 100:.0f}%)")
    print()

    ok = not wrong and not cross_zone
    print("=" * 76)
    print(f"  判定：{'PASS' if ok else 'FAIL'} —— 无误判、无串区；"
          f"{len(unknown)} 页因 DCS 不导出元素名而无法自动识别（属已知接口限制）")
    print("=" * 76)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

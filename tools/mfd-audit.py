"""MFD 页面覆盖检测：把中屏的菜单键挨个按一遍，看哪些页面能被识别、哪些认不出。

做什么：
  1. 回主菜单（D3）
  2. 依次按 U1..U5、L1..L4、R1..R5（主菜单的 14 个入口）
  3. 每次按键后读 sys.mfd 的元素名，用「覆盖率」算法匹配 56 个页面
  4. 输出：键 → 预期页面 → 屏幕元素名 → 识别结果（认出 / 认不出 / 认成了别的）

只按 MFD 菜单键，不碰任何飞行状态。跑完把中屏停回主菜单。

用法：python tools/mfd-audit.py [设备号]     # 设备号默认 47
"""

import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

DEV = int(sys.argv[1]) if len(sys.argv) > 1 else 47
BASE = "http://127.0.0.1:8080"
OFFSET = 2502
# 中屏 D3 的**元素号** = 793（762 是左屏的，之前写错过）。
# click() 内部会再加一次 OFFSET，这里必须给元素号，不能给命令号，
# 否则会发出 2502+793+2502 = 5797，第一步「回主菜单」就打空，整轮审计作废。
D3 = 793
KEYS = [("U1", 769), ("U2", 770), ("U3", 771), ("U4", 772), ("U5", 773),
        ("L1", 775), ("L2", 776), ("L3", 777), ("L4", 778),
        ("R1", 783), ("R2", 784), ("R3", 785), ("R4", 786), ("R5", 787)]
WAIT = 1.4               # sys 包是 1Hz，每步至少等一个周期

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with op.open(req, timeout=3) as r:
        return r.read().decode()


def state():
    with op.open(BASE + "/state", timeout=3) as r:
        return json.load(r)


def click(el):
    post("/cmd", {"dev": DEV, "cmd": el + OFFSET, "val": 1})
    time.sleep(0.09)
    post("/cmd", {"dev": DEV, "cmd": el + OFFSET, "val": 0})


def mfd_tokens():
    """等一轮新的 sys 包，返回中屏（C=）的元素名列表。"""
    for _ in range(12):
        s = state().get("sys") or {}
        mfd = s.get("mfd") or ""
        for part in mfd.split("|"):
            k, _, v = part.partition("=")
            if k == "C":
                return [x for x in v.split(",") if x]
        time.sleep(0.15)
    return []


# ---- 页面数据 + 覆盖率打分（与 panel.html 的 JS 同一套规则）----
pages = json.loads((Path(__file__).resolve().parent / "mfd-pages.json").read_text(encoding="utf-8"))
cnt = Counter()
for p in pages.values():
    for x in set(y.rstrip("_") for y in p.get("e", [])):
        cnt[x] += 1
generic = {k for k, v in cnt.items() if v > len(pages) * 0.15} | {"split_white_line"}


def rank(tokens):
    res = []
    for pid, p in pages.items():
        pre = {x.rstrip("_") for x in p.get("e", []) if x.rstrip("_") not in generic}
        if not pre:
            continue
        hit = sum(1 for n in tokens if any(n.startswith(q) for q in pre))
        cov = hit / len(tokens) if tokens else 0
        if hit >= 1 and cov >= 0.4:
            res.append((round(cov, 2), hit, pid))
    return sorted(res, reverse=True)[:3]


def main():
    st = state()
    if not st.get("has_data"):
        print("DCS 没有在发数据 —— 先进任务（进座舱），再跑。")
        return
    if "JF-17" not in str((st.get("sys") or {}).get("ac", "")):
        print("当前机型不是 JF-17，这套键位不适用。")
        return

    print("回主菜单…")
    click(D3)
    time.sleep(WAIT)

    rows = []
    for key, el in KEYS:
        click(el)
        time.sleep(WAIT)
        tokens = mfd_tokens()
        top = rank(tokens)
        best = top[0] if top else (0, 0, "（认不出）")
        rows.append((key, best, tokens))
        print(f"{key:3s} → {best[2]:24s} 覆盖 {best[0]:.2f}（命中 {best[1]}）"
              f"   元素 {tokens[:8]}{'…' if len(tokens) > 8 else ''}")

    # 走完回主菜单
    click(D3)
    print("\n已回主菜单。")

    print("\n===== 汇总 =====")
    for key, (cov, hit, pid), tokens in rows:
        flag = "✅" if cov >= 0.45 else "❓ 认不出"
        print(f"{key:3s} {pid:26s} 覆盖 {cov:.2f}  {flag}")
    unknown = [(k, t) for k, (c, h, p), t in rows if c < 0.45]
    if unknown:
        print("\n—— 认不出的页面（这些就是要补进识别表的）——")
        for k, tokens in unknown:
            print(f"{k}: {tokens}")


if __name__ == "__main__":
    main()

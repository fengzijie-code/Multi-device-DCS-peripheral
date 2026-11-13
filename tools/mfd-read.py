"""从屏幕固定角落读三块 MFD，认出各自停在哪一页。

前提：DCS 里显示器配置选成 `MFD Tap (JF17)`
（文件在 Saved Games/DCS/Config/MonitorSetup/MFD_tap.lua）。
这样三块 MFD 会被画在屏幕左下角固定位置，跟视角、头动无关。
识别不靠 DCS 接口 —— DCS 根本不导出页面状态，只能看画面。

用法：
    python tools/mfd-read.py --check      # 只报亮度，确认视口有没有画出来
    python tools/mfd-read.py              # 抓三块 + 识别页面，存图并打印结果
    python tools/mfd-read.py --save x.png # 顺带把中屏存成文件
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageGrab

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / ".tmp"

MF_W, MF_H = 200, 267          # 必须和 MFD_tap.lua 里的 MF_W / MF_H 一致
SCREENS = {"left": 0, "center": 1, "right": 2}
UPSCALE = 3                    # OCR 前放大：200px 宽的屏上字只有十来个像素

_ocr = None


def ocr_engine():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def grab_all():
    full = ImageGrab.grab()                      # 只要主屏
    w, h = full.size
    y = h - MF_H
    return {k: full.crop((i * MF_W, y, (i + 1) * MF_W, y + MF_H)) for k, i in SCREENS.items()}


def brightness(im):
    px = list(im.convert("L").getdata())
    return sum(px) / len(px)


def tokens_of(img):
    """OCR 出词，做归一化：大写、去空白和非字母数字（'40-' → '40'）。"""
    big = img.resize((img.width * UPSCALE, img.height * UPSCALE), Image.LANCZOS)
    res, _ = ocr_engine()(big)
    raw = [r[1] for r in (res or [])]
    toks = []
    for t in raw:
        s = re.sub(r"[^A-Za-z0-9.]", "", t).upper()
        if s:
            toks.append(s)
    return raw, toks


def load_pages():
    return json.loads((HERE / "mfd-pages.json").read_text(encoding="utf-8"))


def identify(toks, pages):
    """按「这个页面上有哪些标签」给每个页面打分。

    长标签权重高（CNTL/CHKLS 这种比 1、2 有区分度）；
    页名（U1 通常是页面名）额外加分。
    """
    tset = set(toks)
    scores = {}
    for pid, p in pages.items():
        labels = {re.sub(r"[^A-Za-z0-9.]", "", str(v).replace("\\n", "")).upper()
                  for v in p.get("k", {}).values()}
        labels.discard("")
        if not labels:
            continue
        hit = 0.0
        for lab in labels:
            if lab in tset:
                hit += max(2, len(lab))
        # 页名多半写在 U1 上
        u1 = re.sub(r"[^A-Za-z0-9.]", "", str(p.get("k", {}).get("U1", ""))).upper()
        if u1 and u1 in tset:
            hit += 6
        if hit:
            scores[pid] = hit / (len(labels) ** 0.5)   # 除以标签数的平方根，避免页标签多就占便宜
    return sorted(scores.items(), key=lambda kv: -kv[1])


def main():
    check = "--check" in sys.argv
    save = None
    if "--save" in sys.argv:
        save = sys.argv[sys.argv.index("--save") + 1]

    OUT.mkdir(exist_ok=True)
    shots = grab_all()
    pages = None if check else load_pages()

    for name, im in shots.items():
        b = brightness(im)
        if check:
            print(f"{name:6s} 亮度 {b:6.1f}  {'黑（视口没生效？）' if b < 8 else '有内容'}")
            continue
        im.save(OUT / f"mfd_live_{name}.png")
        if b < 8:
            print(f"{name:6s} 黑屏，跳过识别")
            continue
        raw, toks = tokens_of(im)
        top = identify(toks, pages)[:3]
        best = top[0] if top else ("?", 0)
        print(f"\n{name:6s} 亮度 {b:5.1f}  OCR: {raw[:12]}")
        print(f"       判定: {best[0]}  分数 {best[1]:.1f}")
        for pid, sc in top[1:]:
            print(f"       备选: {pid} {sc:.1f}")

    if save:
        shots["center"].save(save)
        print("已存", save)


if __name__ == "__main__":
    main()

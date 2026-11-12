"""对 tools/panel.html 做一次真实渲染验收（需要 playwright + 本机 Chrome）。

三个视口各截一张，顺带收集 console 报错和页面上每个数字位的实际文本 ——
截图只能看出「有没有排版炸掉」，文本才验得出「数字对不对」。

用法：
    python tools/check-panel.py                          # 默认 8080
    python tools/check-panel.py http://127.0.0.1:8091/panel .tmp

配合 tools/mock_export.py + tools/fake-phone.py 一起用，才有数据可看：
    python tools/mock_export.py --target 127.0.0.1:5010 --duration 45
    python tools/fake-phone.py 8080 45 999
"""
import json
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/panel"
OUT = sys.argv[2] if len(sys.argv) > 2 else ".tmp"

VIEWPORTS = [
    ("ipad-land", 1024, 768, 2),
    ("ipad-port", 768, 1024, 2),
    ("phone", 412, 915, 2),
]

FIELDS = ["wpn", "wcnt", "cn", "wlist", "radar", "endur2", "ff2",
          "fuel", "fuelin", "fuelx", "ff", "endur", "fuelnote",
          "rpml", "templ", "hydl", "ias", "alt", "mach", "hdg", "g",
          "agl", "ias2", "vs", "gear", "flaps", "sbrk", "wbrake", "canopy",
          "status", "aircraft"]

with sync_playwright() as p:
    # 本机 playwright 的 chromium 版本和已下载的对不上（1248 vs 1243），
    # 直接用系统装的 Chrome，省一次几百兆的下载。
    b = p.chromium.launch(channel="chrome")
    for name, w, h, dpr in VIEWPORTS:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr)
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}")
              if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.goto(URL, wait_until="load")
        pg.wait_for_timeout(3000)          # 让它至少拉两轮 /state

        vals = {}
        for f in FIELDS:
            el = pg.query_selector(f"#{f}")
            vals[f] = el.inner_text() if el else "<缺失>"
        note = pg.query_selector("#trimnote")
        vals["trimnote"] = note.inner_text() if note else "<缺失>"
        frozen = pg.query_selector("#frozen")
        vals["_frozen_visible"] = bool(frozen and frozen.is_visible())
        # 卡片有没有横向溢出（移动端最常见的排版事故）
        overflow = pg.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.card').forEach((c, i) => {
                if (c.scrollWidth > c.clientWidth + 1)
                    out.push({i, title: c.querySelector('h2').textContent,
                              scroll: c.scrollWidth, client: c.clientWidth});
            });
            return {cards: out, bodyScroll: document.body.scrollWidth,
                    bodyClient: document.body.clientWidth};
        }""")
        pg.screenshot(path=f"{OUT}/panel-{name}.png", full_page=True)

        print(f"\n=== {name} {w}x{h} ===")
        print(json.dumps(vals, ensure_ascii=False, indent=1))
        print("overflow:", json.dumps(overflow, ensure_ascii=False))
        print("console:", errs or "干净")
        ctx.close()
    b.close()
print("\n截图:", f"{OUT}/panel-*.png")

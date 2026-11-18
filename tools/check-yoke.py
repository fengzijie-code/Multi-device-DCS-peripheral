"""对 /yoke 做一次真渲染 + 真触摸验收（需要 playwright + 本机 Chrome）。

用法：
    python tools/check-yoke.py                        # 默认 http://127.0.0.1:8080/yoke
    python tools/check-yoke.py https://127.0.0.1:8443/yoke

验的是「手指推上去，/input 里到底收到了什么」—— 截图只能看版面，
触摸语义（上推是不是拉杆、松手有没有回中、油门有没有被误发 0）必须看数据。
https 下还会用 CDP 的 DeviceOrientation 假造倾斜，验体感那条轴；
http 下则验「点体感会明确告诉你缺 HTTPS」。
"""
import json
import ssl
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/yoke"
BASE = URL.rsplit("/yoke", 1)[0]
W, H = 1194, 834          # 11 吋 iPad Pro 横屏的 CSS 视口

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def snap():
    with urllib.request.urlopen(f"{BASE}/input", context=_SSL) as r:
        return json.load(r)


fails, notes = [], []


def check(name, cond, detail=""):
    (notes if cond else fails).append(f"{'ok ' if cond else 'FAIL'} {name} {detail}")


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": W, "height": H},
                        device_scale_factor=2, has_touch=True,
                        is_mobile=False, locale="zh-CN",
                        ignore_https_errors=True)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL, wait_until="load")
    time.sleep(0.6)

    pg.screenshot(path=".tmp/yoke-ipad.png")
    check("页面 200 且已渲染", pg.title().startswith("DCS 杆"), pg.title())
    check("无 console 报错", not errs, str(errs[:3]))

    # 顶栏数值说明 50Hz 循环已跑起来
    time.sleep(1.2)
    hz = pg.inner_text("#hz")
    rtt = pg.inner_text("#rtt")
    check("发包率 ~50Hz", hz.isdigit() and 30 <= int(hz) <= 60, f"hz={hz}")
    check("RTT 有值", "峰" in rtt, f"rtt={rtt}")
    s0 = snap()
    g = s0.get("gap_ms") or {}
    check("服务端到达帧率 ≈ 50Hz",
          g.get("rate_hz") is not None and 40 <= g["rate_hz"] <= 60, str(g))
    check("服务端有帧间隔峰值", g.get("max_ms") is not None, str(g))
    # 回包里要带 g（帧间隔峰），HUD 靠它显示抖动
    with urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/input", data=b'{"x":0,"y":0,"r":0,"b":0}',
            headers={"Content-Type": "application/json"}), context=_SSL) as r:
        resp = json.load(r)
    check("POST 回包带 g（帧间隔峰）", "g" in resp, str(resp))

    cdp = ctx.new_cdp_session(pg)

    def touch(kind, x, y, tid=1):
        pt = [{"x": x, "y": y, "id": tid, "radiusX": 12, "radiusY": 12, "force": 1}]
        t = "touchStart" if kind == "start" else ("touchMove" if kind == "move" else "touchEnd")
        cdp.send("Input.dispatchTouchEvent",
                 {"type": t, "touchPoints": pt if kind != "end" else []})

    # ---- 杆盘：从中心往上推
    box = pg.eval_on_selector("#pad", "el=>{const r=el.getBoundingClientRect();"
                                      "return {x:r.x,y:r.y,w:r.width,h:r.height}}")
    check("杆盘是正方形", abs(box["w"] - box["h"]) < 2, f"{box['w']:.0f}x{box['h']:.0f}")
    check("杆盘够大（>=400px）", box["w"] >= 400, f"{box['w']:.0f}px")
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    touch("start", cx, cy)
    touch("move", cx, cy - box["h"] * 0.2)
    time.sleep(0.18)
    s = snap()
    check("上推 = y 正（拉杆）", s["axes"]["y"] > 0.4, f"y={s['axes']['y']:.2f}")
    check("上推不动横滚", abs(s["axes"]["x"]) < 0.05, f"x={s['axes']['x']:.2f}")

    touch("move", cx + box["w"] * 0.22, cy)
    time.sleep(0.18)
    s = snap()
    check("右推 = x 正（右滚）", s["axes"]["x"] > 0.45, f"x={s['axes']['x']:.2f}")

    # 推过头：锚点跟随，输出必须被夹在 1.0
    touch("move", cx + box["w"] * 0.9, cy)
    time.sleep(0.18)
    s = snap()
    check("推过头仍夹在 1.0", 0.95 <= s["axes"]["x"] <= 1.0, f"x={s['axes']['x']:.3f}")

    touch("end", 0, 0)
    time.sleep(0.18)
    s = snap()
    check("松手回中 x/y=0", abs(s["axes"]["x"]) < 0.02 and abs(s["axes"]["y"]) < 0.02,
          str(s["axes"]))

    # ---- 油门：还没碰过时不能发 t（否则飞机被拽到慢车）
    check("未接管时不发 t", "t" not in s["axes"] or s["axes"]["t"] is None,
          str(s["axes"].get("t")))

    tb = pg.eval_on_selector("#thr", "el=>{const r=el.getBoundingClientRect();"
                                     "return {x:r.x,y:r.y,w:r.width,h:r.height}}")
    touch("start", tb["x"] + tb["w"] / 2, tb["y"] + tb["h"] * 0.25, tid=2)
    time.sleep(0.18)
    s = snap()
    check("油门上 1/4 处 ≈ 75%", abs(s["axes"]["t"] - 0.75) < 0.05, f"t={s['axes']['t']:.2f}")
    touch("end", 0, 0, tid=2)
    time.sleep(0.25)
    s = snap()
    check("油门松手保持", abs(s["axes"]["t"] - 0.75) < 0.05, f"t={s['axes']['t']:.2f}")

    # ---- 按钮：机炮 BTN12 = bit11
    gb = pg.eval_on_selector('[data-bit="11"]', "el=>{const r=el.getBoundingClientRect();"
                                               "return {x:r.x+r.width/2,y:r.y+r.height/2}}")
    touch("start", gb["x"], gb["y"], tid=3)
    time.sleep(0.18)
    s = snap()
    check("机炮按下 = bit11", s["buttons"] & (1 << 11), f"b={s['buttons']}")
    touch("end", 0, 0, tid=3)
    time.sleep(0.18)
    s = snap()
    check("机炮松开 = 清零", not (s["buttons"] & (1 << 11)), f"b={s['buttons']}")

    # ---- 脚舵：左舵 = r 负
    rb = pg.eval_on_selector('[data-axis="r"]', "el=>{const r=el.getBoundingClientRect();"
                                              "return {x:r.x+r.width/2,y:r.y+r.height/2}}")
    touch("start", rb["x"], rb["y"], tid=4)
    time.sleep(0.18)
    s = snap()
    check("左舵 = r 负", s["axes"]["r"] < -0.9, f"r={s['axes']['r']}")
    touch("end", 0, 0, tid=4)

    # ---- 体感：https 下用 CDP 假造倾斜；http 下验"会说缺 HTTPS"
    secure = pg.evaluate("window.isSecureContext")
    pg.click("#tiltBtn")
    time.sleep(0.25)
    if secure:
        check("https 下不弹引导页", not pg.is_visible("#tlsSheet"), "")
        def orient(beta, gamma):
            cdp.send("DeviceOrientation.setDeviceOrientationOverride",
                     {"alpha": 0, "beta": beta, "gamma": gamma})
            time.sleep(0.22)

        orient(0, 0)                       # 基准
        check("体感开启后不复位", pg.inner_text("#padTag").startswith("体感"),
              pg.inner_text("#padTag"))
        orient(0, 15)                      # 右倾 15° -> x = 15/25
        s = snap()
        check("右倾 15° ≈ x 0.6", abs(s["axes"]["x"] - 0.6) < 0.06, f"x={s['axes']['x']:.3f}")
        orient(-12, 15)
        s = snap()
        check("前倾 12° ≈ y -0.48", abs(s["axes"]["y"] + 0.48) < 0.08, f"y={s['axes']['y']:.3f}")

        pg.click("#zeroBtn")               # 当前姿态记为中立
        time.sleep(0.25)
        s = snap()
        check("校零后回 0", abs(s["axes"]["x"]) < 0.03 and abs(s["axes"]["y"]) < 0.03,
              f"x={s['axes']['x']:.3f} y={s['axes']['y']:.3f}")

        orient(0, 60)                      # 超过行程
        s = snap()
        check("体感超行程夹在 1.0", 0.95 <= s["axes"]["x"] <= 1.0, f"x={s['axes']['x']:.3f}")

        pg.click("#tiltBtn")               # 关掉
        time.sleep(0.3)
        s = snap()
        check("关体感后 x 回 0", abs(s["axes"]["x"]) < 0.03, f"x={s['axes']['x']:.3f}")
        cdp.send("DeviceOrientation.clearDeviceOrientationOverride")
    else:
        # 缺 https 时不该只弹一句 6 秒就消失的 toast —— 要铺出能照着做的引导页。
        with urllib.request.urlopen(f"{BASE}/info", context=_SSL) as r:
            info = json.load(r)
        port = info.get("https_port") or 0
        check("http 下点体感弹出引导页", pg.is_visible("#tlsSheet"), "")
        url_val = pg.input_value("#tsUrl")
        host = pg.evaluate("location.hostname")
        check("引导页给出 https 地址", url_val == f"https://{host}:{port}/yoke",
              f"{url_val} port={port}")
        check("引导页带证书下载入口",
              "ca.mobileconfig" in (pg.get_attribute("#tsProf", "href") or ""), "")
        pg.screenshot(path=".tmp/yoke-tls.png", full_page=False)
        # 引导页要能滚（body 上 global 禁了 touchmove，这里必须放行）
        check("引导页可滚动",
              pg.evaluate("() => {const s=document.querySelector('#tlsSheet');"
                          "return getComputedStyle(s).overflowY === 'auto' && s.scrollHeight > s.clientHeight}"),
              "")
        for p_ in ("/ca.mobileconfig", "/ca-mobileconfig"):
            with urllib.request.urlopen(f"{BASE}{p_}", context=_SSL) as r:
                ctype = r.headers.get("Content-Type", "")
                body = r.read()
            check(f"描述文件可直接下载 {p_}",
                  "aspen-config" in ctype and b"PayloadType" in body,
                  f"{ctype} {len(body)}B")
        pg.click("#tsClose")
        time.sleep(0.2)
        check("关掉引导页", not pg.is_visible("#tlsSheet"), "")

    # ---- 各区域不能溢出视口
    over = pg.evaluate("""() => {
      const out = [];
      document.querySelectorAll('#deck *, #hud *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width > 1 && (r.right > innerWidth + 1 || r.bottom > innerHeight + 1
            || r.left < -1 || r.top < -1)) out.push(el.id || el.className);
      });
      return out.slice(0, 8);
    }""")
    check("没有元素溢出视口", not over, str(over))

    # 竖屏也照一张（万一有人竖着放）
    pg.set_viewport_size({"width": 834, "height": 1194})
    time.sleep(0.4)
    pg.screenshot(path=".tmp/yoke-ipad-port.png")
    pg.set_viewport_size({"width": W, "height": H})
    time.sleep(0.3)
    pg.screenshot(path=".tmp/yoke-ipad-land2.png")

    ctx.close()
    b.close()

print("\n".join(notes))
print("\n".join(fails) if fails else "\n全部通过 %d 项" % len(notes))
sys.exit(1 if fails else 0)

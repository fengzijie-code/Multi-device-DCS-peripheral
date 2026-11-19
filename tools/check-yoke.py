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

    # ---- 仪表条：/state 的 1Hz 帧要真的落到界面上（需要 mock_export 在喂遥测）
    pg.wait_for_function("() => document.querySelector('#sIas').textContent !== '--'",
                         timeout=6000)
    ias = pg.inner_text("#sIas").strip()
    alt = pg.inner_text("#sAlt").strip()
    hdg = pg.inner_text("#sHdg").strip()
    check("仪表条有读数", ias.isdigit() and int(ias) > 0, f"ias={ias}")
    check("高度有读数", alt.isdigit() and int(alt) > 0, f"alt={alt}")
    check("航向有读数", hdg.isdigit() and 0 <= int(hdg) <= 360, f"hdg={hdg}")
    tf = pg.evaluate("getComputedStyle(document.querySelector('#adiDisc')).transform")
    check("姿态球有姿态", tf not in ("", "none", "matrix(1, 0, 0, 1, 0, 0)"), tf)
    # 玻璃 HUD：状态/读数/按钮全是浮在画面上的，deck 铺满全屏。
    # 所以"不压"要看它们跟杆盘的关系，而不是跟 deck 的盒子关系。
    geo = pg.evaluate("""() => {
      const b = s => document.querySelector(s).getBoundingClientRect();
      const st = b('#strip'), pd = b('#pad'), hud = b('#hud');
      const kn = document.querySelector('#thrKnob').getBoundingClientRect();
      return {stripH: Math.round(st.height), padBottom: Math.round(pd.bottom),
              stripTop: Math.round(st.top), hudBottom: Math.round(hud.bottom),
              padTop: Math.round(pd.top),
              knobInThr: kn.top >= b('#thr').top - 30 && kn.bottom <= b('#thr').bottom + 30};
    }""")
    check("底部读数条不压杆盘", geo["padBottom"] <= geo["stripTop"] + 1, str(geo))
    check("顶部状态行不压杆盘", geo["padTop"] >= geo["hudBottom"] - 1, str(geo))
    check("读数条高度合理", 36 <= geo["stripH"] <= 64, str(geo["stripH"]))
    check("油门圆徽章骑在竖条上", geo["knobInThr"], str(geo))

    # iPad 主屏模式下状态栏（时间 / 电量）会盖在页面顶上，
    # 顶上一排必须整体让开 —— 这条是用户实测撞出来的，别再挪回去。
    topmost = pg.evaluate("""() => {
      const els = [...document.querySelectorAll('#hud > *, #tabs > *, #ops > *')]
        .filter(e => e.getBoundingClientRect().width > 0);   // 跳过 display:none 的隐藏 chip
      return Math.min(...els.map(e => e.getBoundingClientRect().top));
    }""")
    check("顶部留出让开状态栏", topmost >= 34, f"top={topmost:.0f}px")

    # 脚舵在右下：贴右边缘、在右侧按钮列下面、并且不压底部读数条
    rl = pg.evaluate("""() => {
      const b = s => document.querySelector(s).getBoundingClientRect();
      const r = b('#rud'), col = b('#colTakeoff'), st = b('#strip'), pd = b('#pad');
      return {right: Math.round(innerWidth - r.right), top: Math.round(r.top),
              colBottom: Math.round(col.bottom), stripTop: Math.round(st.top),
              padRight: Math.round(pd.right), rudLeft: Math.round(r.left)};
    }""")
    check("脚舵贴右下角", rl["right"] <= 32 and rl["rudLeft"] > rl["padRight"],
          str(rl))
    check("脚舵不压按钮列", rl["top"] >= rl["colBottom"] - 1, str(rl))
    check("脚舵不压读数条", rl["top"] + 76 <= rl["stripTop"] + 1, str(rl))

    # 解锁键在左下角、做成大圆 —— 用户实测：原来那颗顶部 chip 不好上锁
    ab = pg.evaluate("""() => {
      const b = s => document.querySelector(s).getBoundingClientRect();
      const a = b('#armBtn'), th = b('#thr'), st = b('#strip'), pd = b('#pad');
      return {left: Math.round(a.left), bottom: Math.round(innerHeight - a.bottom),
              w: Math.round(a.width), h: Math.round(a.height),
              top: Math.round(a.top), thrBottom: Math.round(th.bottom),
              stripTop: Math.round(st.top), padLeft: Math.round(pd.left)};
    }""")
    check("解锁键贴左下角", ab["left"] <= 32 and ab["bottom"] <= 80
          and ab["left"] + ab["w"] <= ab["padLeft"], str(ab))
    check("解锁键够大（拇指不用瞄）", ab["w"] >= 96 and ab["h"] >= 96, str(ab))
    check("解锁键不压油门杆", ab["top"] >= ab["thrBottom"] - 1, str(ab))
    check("解锁键不压读数条", ab["top"] + ab["h"] <= ab["stripTop"] + 1, str(ab))

    # ---- 四页（照 Pixel：仪表/起降/战斗/校准）
    def page_of():
        return pg.eval_on_selector("#app", "el=>el.getAttribute('data-page')")

    def pad_rect():
        return pg.eval_on_selector("#pad", "el=>{const r=el.getBoundingClientRect();"
                                            "return [Math.round(r.x),Math.round(r.y),"
                                            "Math.round(r.width)]}")

    tabs = pg.eval_on_selector_all(
        "#tabs .tb", "els=>els.map(e=>e.getAttribute('data-page'))")
    check("四个页签齐全", tabs == ["pfd", "takeoff", "combat", "calib"], str(tabs))

    r_to = pad_rect()
    pg.click('#tabs .tb[data-page="combat"]')
    time.sleep(0.3)
    r_cb = pad_rect()
    check("切到战斗页", page_of() == "combat", page_of())
    # 这条是整个四页设计的硬约束：换页只换左列内容，杆盘坐标必须一个像素都不动，
    # 否则正在推杆时切页会把杆量甩一下。
    check("切页后杆盘不挪位", r_to == r_cb, f"{r_to} vs {r_cb}")
    vis = pg.evaluate("""() => {
      const d = s => getComputedStyle(document.querySelector(s)).display;
      return {to: d('#colTakeoff'), cb: d('#colCombat')};
    }""")
    check("战斗页只显示战斗面板", vis["to"] == "none" and vis["cb"] == "flex", str(vis))

    pg.click('#tabs .tb[data-page="takeoff"]')
    time.sleep(0.3)
    vis = pg.evaluate("""() => {
      const d = s => getComputedStyle(document.querySelector(s)).display;
      return {to: d('#colTakeoff'), cb: d('#colCombat')};
    }""")
    check("起降页只显示起降面板", vis["to"] == "flex" and vis["cb"] == "none", str(vis))

    # 仪表页：同一份 /state 数据要落到大表上，而且这一页不该有杆盘
    pg.click('#tabs .tb[data-page="pfd"]')
    time.sleep(2.2)
    pfd = pg.evaluate("""() => {
      const g = s => document.querySelector(s);
      const ids = ['#pIas','#pAlt','#pVs','#pAgl','#pHdg','#pG','#pMach','#pAoa','#pRpm','#pFuel'];
      return {vals: ids.map(s => g(s).textContent.trim()),
              tf: getComputedStyle(g('#bAdiDisc')).transform,
              deck: getComputedStyle(g('#deck')).display};
    }""")
    live = [v for v in pfd["vals"] if v not in ("--", "")]
    check("仪表页十个数字都有读数", len(live) == 10, str(pfd["vals"]))
    check("仪表页姿态球有姿态",
          pfd["tf"] not in ("", "none", "matrix(1, 0, 0, 1, 0, 0)"), pfd["tf"])
    check("仪表页收起杆盘", pfd["deck"] == "none", pfd["deck"])
    pg.screenshot(path=".tmp/yoke-pfd.png")

    pg.click('#tabs .tb[data-page="takeoff"]')
    time.sleep(0.3)


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

    # ---- 上锁：默认不发任何操纵量（和 Pixel 端一致）
    check("默认上锁", pg.inner_text("#armTxt").strip() == "解锁", pg.inner_text("#armTxt"))
    touch("start", cx, cy)
    touch("move", cx, cy - box["h"] * 0.2)
    time.sleep(0.18)
    s = snap()
    check("上锁时推杆无输出",
          abs(s["axes"]["x"]) < 0.01 and abs(s["axes"]["y"]) < 0.01, str(s["axes"]))
    touch("end", 0, 0)
    pg.click("#armBtn")
    time.sleep(0.2)
    check("点一下即解锁", "已解锁" in pg.inner_text("#armTxt"), pg.inner_text("#armTxt"))

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

    # ---- 配平：推住杆 → 记配平 → 松手应当「保持」，而不是回中
    touch("start", cx, cy)
    touch("move", cx + box["w"] * 0.2, cy)
    time.sleep(0.15)
    pg.evaluate("document.querySelector('#trimBtn').click()")
    time.sleep(0.1)
    touch("end", 0, 0)
    time.sleep(0.22)
    s = snap()
    check("配平后松手保持杆位", s["axes"]["x"] > 0.3, f"x={s['axes']['x']:.2f}")
    pg.evaluate("document.querySelector('#trimClr').click()")
    time.sleep(0.22)
    s = snap()
    check("清配平后回中", abs(s["axes"]["x"]) < 0.02, f"x={s['axes']['x']:.2f}")

    # ---- 校准页（原来是「手感」弹窗，现在是一整页）
    pg.click("#setBtn")
    time.sleep(0.3)
    check("校准页能打开", pg.is_visible("#pageCalib") and page_of() == "calib", page_of())
    pg.screenshot(path=".tmp/yoke-set.png")
    pg.eval_on_selector("#rRange",
                        "el=>{el.value=40;el.dispatchEvent(new Event('input',{bubbles:true}))}")
    time.sleep(0.12)
    check("滑块改动生效", pg.inner_text("#vRange").strip() == "40°", pg.inner_text("#vRange"))
    pg.click("#setReset")
    time.sleep(0.12)
    check("恢复默认", pg.inner_text("#vRange").strip() == "22°", pg.inner_text("#vRange"))
    pg.click("#setClose")
    time.sleep(0.3)
    check("校准页能退回起降页",
          not pg.is_visible("#pageCalib") and page_of() == "takeoff", page_of())

    # ---- 按钮最短脉冲：DCS 按模拟帧采样，20ms 的快速点按会丢
    # 机炮在战斗页，先切过去
    pg.click('#tabs .tb[data-page="combat"]')
    time.sleep(0.3)
    gb0 = pg.eval_on_selector('[data-bit="11"]',
                              "el=>{const r=el.getBoundingClientRect();"
                              "return {x:r.x+r.width/2,y:r.y+r.height/2}}")
    touch("start", gb0["x"], gb0["y"], tid=5)
    touch("end", 0, 0, tid=5)          # 立刻抬起，中间不留时间
    time.sleep(0.06)
    s = snap()
    check("快速点按仍被按下（最短 120ms）", bool(s["buttons"] & (1 << 11)),
          f"b={s['buttons']}")
    time.sleep(0.30)
    s = snap()
    check("脉冲到点后自动松开", not (s["buttons"] & (1 << 11)), f"b={s['buttons']}")

    # 回到起降页，后面全是油门/脚舵
    pg.click('#tabs .tb[data-page="takeoff"]')
    time.sleep(0.3)

    # ---- 油门：还没碰过时不能发 t（否则飞机被拽到慢车）
    check("未接管时不发 t", "t" not in s["axes"] or s["axes"]["t"] is None,
          str(s["axes"].get("t")))

    # 油门默认反转（invT 默认开，补偿 DCS 那边反着的轴向）：
    # 发送值 = 1 − 手指位置；但**屏上旋钮必须跟着手走** —— 这条是
    # 「手往上、屏上油门往下」那次翻车的验收，反转永远不许碰显示层。
    tb = pg.eval_on_selector("#thr", "el=>{const r=el.getBoundingClientRect();"
                                     "return {x:r.x,y:r.y,w:r.width,h:r.height}}")
    touch("start", tb["x"] + tb["w"] / 2, tb["y"] + tb["h"] * 0.25, tid=2)
    time.sleep(0.18)
    s = snap()
    check("油门上 1/4 处发送值 ≈ 25%（默认反转）",
          abs(s["axes"]["t"] - 0.25) < 0.05, f"t={s['axes']['t']:.2f}")
    knob = pg.evaluate("""() => {
      const k = document.querySelector('#thrKnob').getBoundingClientRect();
      const t = document.querySelector('#thr').getBoundingClientRect();
      return {knobTop: k.top + k.height / 2 - t.top, thrH: t.height};
    }""")
    check("屏上油门旋钮跟着手走（停在手指的上 1/4）",
          abs(knob["knobTop"] - tb["h"] * 0.25) < tb["h"] * 0.12,
          f"knob@{knob['knobTop']:.0f}px / {knob['thrH']:.0f}px")
    touch("end", 0, 0, tid=2)
    time.sleep(0.25)
    s = snap()
    check("油门松手保持", abs(s["axes"]["t"] - 0.25) < 0.05, f"t={s['axes']['t']:.2f}")

    # ---- 上锁时油门字段必须消失（缺 t = 别动油门，发 0 = 拽到慢车）
    pg.click("#armBtn")
    time.sleep(0.25)
    s = snap()
    check("上锁后不再发 t", s["axes"].get("t") is None, str(s["axes"].get("t")))
    pg.click("#armBtn")
    time.sleep(0.25)
    s = snap()
    check("解锁后油门值还在", s["axes"].get("t") is not None
          and abs(s["axes"]["t"] - 0.25) < 0.05, str(s["axes"].get("t")))

    # ---- 按钮：机炮 BTN12 = bit11（战斗页）
    pg.click('#tabs .tb[data-page="combat"]')
    time.sleep(0.3)
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

    pg.click('#tabs .tb[data-page="takeoff"]')
    time.sleep(0.3)

    # ---- 脚舵：比例滑块（不是两个满舵按钮），松手回中
    rb = pg.eval_on_selector("#rud", "el=>{const r=el.getBoundingClientRect();"
                                   "return {x:r.x,y:r.y,w:r.width,h:r.height}}")
    check("脚舵是横向滑块", rb["w"] > rb["h"] * 1.5, f"{rb['w']:.0f}x{rb['h']:.0f}")
    rx, ry = rb["x"] + rb["w"] / 2, rb["y"] + rb["h"] / 2
    touch("start", rx, ry, tid=4)
    touch("move", rx + rb["w"] * 0.40, ry, tid=4)     # 滑到约 80% 右
    time.sleep(0.18)
    s = snap()
    check("脚舵右滑 = r 正且是比例值", 0.5 < s["axes"]["r"] <= 1.0,
          f"r={s['axes']['r']:.2f}")
    touch("move", rx - rb["w"] * 0.40, ry, tid=4)
    time.sleep(0.18)
    s = snap()
    check("脚舵左滑 = r 负", -1.0 <= s["axes"]["r"] < -0.5, f"r={s['axes']['r']:.2f}")
    touch("end", 0, 0, tid=4)
    time.sleep(0.2)
    s = snap()
    check("脚舵松手回中", abs(s["axes"]["r"]) < 0.03, f"r={s['axes']['r']:.3f}")

    # ---- 体感：https 下用 CDP 假造倾斜；http 下验"会说缺 HTTPS"
    secure = pg.evaluate("window.isSecureContext")
    pg.click("#tiltBtn")
    time.sleep(0.25)
    if secure:
        check("https 下不弹引导页", not pg.is_visible("#tlsSheet"), "")
        check("顶栏标记 https", pg.inner_text("#sec").strip() == "https",
              pg.inner_text("#sec").strip())
        # 回归：以前把握手做在 accept() 里，一个"连上但不发 ClientHello"的
        # 连接就能把整个 8443 堵死（现象是「刚才还能开，现在打不开」）。
        import socket as _sk
        _host = pg.evaluate("location.hostname")
        _port = int(pg.evaluate("location.port"))
        stuck = _sk.create_connection((_host, _port), timeout=3)
        try:
            t0 = time.time()
            with urllib.request.urlopen(f"{BASE}/info", context=_SSL, timeout=6) as r:
                r.read()
            dt = time.time() - t0
            check("有哑连接占着时 HTTPS 仍能服务", dt < 3.0, f"{dt*1000:.0f}ms")
        finally:
            stuck.close()
        # 同一端口还得吃得下明文：地址栏只写 ip:8443 时 Safari 按 http 发，
        # 只认 TLS 的话表现就是「打不开网页」。
        with urllib.request.urlopen(f"http://{_host}:{_port}/yoke", timeout=5) as r:
            check("TLS 端口也收明文 HTTP", r.status == 200, str(r.status))
        def orient(beta, gamma):
            cdp.send("DeviceOrientation.setDeviceOrientationOverride",
                     {"alpha": 0, "beta": beta, "gamma": gamma})
            time.sleep(0.22)

        orient(0, 0)                       # 基准
        check("体感开启后不复位", pg.inner_text("#padTag").startswith("体感"),
              pg.inner_text("#padTag"))
        # 曲线按 Pixel 端默认值：死区 2.5°、行程 22°、expo 0.35
        #   15° → v=(15-2.5)/19.5=0.641 → 0.641*0.65 + 0.641³*0.35 ≈ 0.509
        orient(0, 15)                      # 右倾 15°
        s = snap()
        check("右倾 15° ≈ x 0.51", abs(s["axes"]["x"] - 0.509) < 0.06, f"x={s['axes']['x']:.3f}")

        # 手感参数必须真的进到曲线里，不能只是 UI 上动了个数字：
        # 满行程 22° → 40°，同样倾 15° 的输出应当明显变小（约 0.23）
        pg.click("#setBtn"); time.sleep(0.15)
        pg.eval_on_selector("#rRange",
                            "el=>{el.value=40;el.dispatchEvent(new Event('input',{bubbles:true}))}")
        pg.click("#setClose"); time.sleep(0.15)
        orient(0, 16); orient(0, 15)       # 逼出一次事件，让曲线用新参数重算
        s = snap()
        check("满行程调大后输出变小", s["axes"]["x"] < 0.35, f"x={s['axes']['x']:.3f}")
        pg.click("#setBtn"); time.sleep(0.12)
        pg.click("#setReset"); pg.click("#setClose"); time.sleep(0.15)
        orient(0, 16); orient(0, 15)
        # 12° → v=(12-2.5)/19.5=0.487 → 0.487*0.65 + 0.487³*0.35 ≈ 0.357
        orient(-12, 15)
        s = snap()
        check("前倾 12° ≈ y -0.36", abs(s["axes"]["y"] + 0.357) < 0.08, f"y={s['axes']['y']:.3f}")
        # 死区内必须严格为 0：手持微抖不该让杆一直轻颤
        orient(0, 1.5)
        s = snap()
        check("死区内输出为 0", abs(s["axes"]["x"]) < 0.01, f"x={s['axes']['x']:.3f}")

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
        check("顶栏标记 http", pg.inner_text("#sec").strip() == "http",
              pg.inner_text("#sec").strip())
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

    # ---- 脚舵：数值在上、滑轨带在中、说明在下，三者不能叠（曾经 fill 用 top/bottom:9px 把字盖了）
    rg = pg.evaluate("""() => {
      const v = document.querySelector('#rudVal').getBoundingClientRect();
      const t = document.querySelector('#rudTag').getBoundingClientRect();
      const f = document.querySelector('#rudFill').getBoundingClientRect();
      return {vB: Math.round(v.bottom), fT: Math.round(f.top),
              fB: Math.round(f.bottom), tT: Math.round(t.top)};
    }""")
    check("脚舵数值/说明不被滑轨压住",
          rg["fT"] >= rg["vB"] - 1 and rg["fB"] <= rg["tT"] + 1, str(rg))

    # 这套皮只做横屏（用户明确：不会有竖排），所以不再拍竖屏。
    pg.screenshot(path=".tmp/yoke-ipad-land2.png")
    pg.set_viewport_size({"width": W, "height": H})
    time.sleep(0.3)
    pg.screenshot(path=".tmp/yoke-ipad-land2.png")

    ctx.close()
    b.close()

print("\n".join(notes))
print("\n".join(fails) if fails else "\n全部通过 %d 项" % len(notes))
sys.exit(1 if fails else 0)

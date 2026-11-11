"""实时盯 /state，把「有没有数据、慢变量来没来」打成一行行滚动的日志。

为什么要它：联调时唯一重要的问题是「现在卡在哪一跳」。
    had_data=0                 → 上游一帧都没到（DCS 没进座舱 / Export.lua 没加载）
    has_data=1 但 sys=-        → 主帧到了，慢变量没到（Export.lua 是旧版）
    has_data=1 且 sys=ok       → 全通
这三种状态只看一次 curl 容易误判，看滚动才有意义。

用法：
    python tools/watch-state.py            # 默认 8080
    python tools/watch-state.py 8091
"""
import json
import sys
import time
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8080"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
URL = f"http://127.0.0.1:{PORT}/state"

prev = None
t0 = time.time()
last_print = -99
while True:
    try:
        st = json.loads(OPENER.open(URL, timeout=2).read())
    except Exception as e:
        print(f"[{time.time()-t0:6.1f}s] 连不上桥接: {e}")
        time.sleep(1.0)
        continue

    sysd = st.get("sys")
    frame = st.get("frame")
    live = st.get("has_data")
    hz = st["stats"]["hz"]
    age = st["stats"]["age_ms"]
    sys_age = st.get("sys_age_ms")

    if not live:
        state = "无主帧"
    elif not sysd:
        state = "有主帧·无慢变量"
    else:
        state = "全通"

    # 状态变化一定打，其余每 2 秒打一次，避免刷屏
    now = time.time()
    sec = int(now - t0)
    if state != prev or sec - last_print >= 2:
        last_print = sec
        line = f"[{now-t0:6.1f}s] {state:<16}"
        if live and frame:
            line += (f" {hz:5.1f}Hz age={age:>4}ms"
                     f" alt={frame['alt']:7.1f}m ias={frame['ias']:6.1f}")
        elif age is not None:
            line += f" age={age}ms"
        if sysd:
            # slow 变量里任何一个都可能是 null（机型不提供），一律走这个包装，
            # 否则 f-string 格式化 None 直接抛 TypeError，整个盯盘脚本就死了。
            def f(v, spec, unit=""):
                return f"{v:{spec}}{unit}" if v is not None else "--"

            line += (f" | fuel={f(sysd.get('fuel'), '7.1f', 'kg')}"
                     f" rpm={f(sysd.get('rpm_l'), '.0f')}"
                     f" cs_e={f(sysd.get('cs_e'), '+.4f')}"
                     f" ff={f(sysd.get('ff'), '.0f')}"
                     f" (慢变量 {sys_age}ms 前)")
        else:
            line += f" | 慢变量: {'从未收到' if sys_age is None else f'已失效 {sys_age}ms'}"
        inp = st.get("input") or {}
        if inp.get("live"):
            line += f" | 杆 x={inp['x']:+.2f} y={inp['y']:+.2f}"
        print(line)
        prev = state

    time.sleep(0.5)

"""假手机 —— 50Hz 往桥接的 /input 打杆量，代替真机做联调。

为什么需要它：辅助面板的「配平估读」只有在**杆回中**时才取样，而判断杆
回没回中用的是手机发来的操纵量。没有真机、或者手上只有 iPad 的时候，
这条链路就没法验证 —— 这个脚本就是补这一段的。

用法：
    python tools/fake-phone.py                      # 默认 8080 端口，前 8 秒回中、之后推满
    python tools/fake-phone.py 8091 60 999          # 端口 8091，跑 60 秒，全程回中
    python tools/fake-phone.py 8080 20 0            # 全程推满（验证「保持」分支）

参数：端口、运行秒数、前 N 秒保持回中。
"""
import json
import sys
import time
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8080"
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
# 前 CENTER_S 秒杆回中（触发配平采样），之后推到一边（触发保持）
CENTER_S = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
# 本机有 HTTP 代理时，urllib 会连 127.0.0.1 也走代理 —— 必须显式绕开，
# 否则表现为「beacon 明明活着，脚本却连接被拒」。
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

t0 = time.time()
n = 0
while time.time() - t0 < DUR:
    el = time.time() - t0
    if el < CENTER_S:
        body = {"x": 0.02, "y": -0.01, "r": 0.0, "t": 0.62, "b": 0}
    else:
        body = {"x": 0.55, "y": 0.42, "r": 0.1, "t": 0.62, "b": 0}
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/input",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        OPENER.open(req, timeout=1.0).read()
        n += 1
    except Exception as e:
        print("post failed:", e)
    time.sleep(0.02)
print(f"fake phone: {n} posts")

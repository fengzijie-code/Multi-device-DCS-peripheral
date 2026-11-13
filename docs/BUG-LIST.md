# Bug 清单（2026-11-13 主动完整测试）

> 来源：`tests/integration_test.py` 第一轮 82 项测试，66 通过 / 16 失败。
> 16 个失败项归并为 **13 个独立缺陷**（部分缺陷被多个用例同时命中）。
> 严重度：P0 阻断 / P1 严重 / P2 一般 / P3 轻微。

| ID | 级别 | 标题 | 命中用例 | 状态 |
|---|---|---|---|---|
| BUG-01 | **P0** | 遥测里的 NaN/Inf 被原样输出成非法 JSON | T-TLM-004 | 已修复 |
| BUG-02 | **P0** | 畸形慢变量包会让 UDP 监听线程直接死掉 | T-TLM-005 | 已修复 |
| BUG-03 | **P0** | 命令文件单槽覆盖，连发两条丢一条 | T-CMD-006 | 已修复 |
| BUG-04 | **P1** | 真实 DCS 结构下 `cs_a/cs_e/cs_r/gr` 永远是 null | T-TLM-002b | 已修复 |
| BUG-05 | **P1** | `/cmd` 接受非法数值/设备号，写出不可解析命令且谎报成功 | T-CMD-007 | 已修复 |
| BUG-06 | **P1** | 屏幕回传能把下半区页面写进上半区，导致上半区按键全失灵 | T-MFD-006 | 已修复 |
| BUG-07 | **P2** | MFD 按键回传不持久化；新页面重放历史按键导致刷新跳页 | T-MFD-007 / T-MFD-008 | 已修复 |
| BUG-08 | **P2** | 单元测试 `EXPECTED_SYS_FIELDS` 落后于 Export.lua，套件常红 | T-STAT-005 / T-REG-001 | 已修复 |
| BUG-09 | **P2** | `mfd-audit.py` 的 D3 被加了两次偏移 | T-STAT-007 / T-MFD-012 | 已修复 |
| BUG-10 | **P2** | `check-panel.py` 溢出报告取 `h2`（不存在），一溢出就崩 | T-STAT-008 / T-REG-002b | 已修复 |
| BUG-11 | **P3** | `vjoy_out.py` 心跳 URL 带尾斜杠时变成 `//vjoy` | T-STAT-009 | 已修复 |
| BUG-12 | **P2** | 设备方法抛异常时仍报 `D0` 成功回执（假回执） | T-CMD-010 | 已修复 |
| BUG-13 | — | （保留号，未使用） | — | — |

---

## BUG-01 · NaN/Inf 被输出成非法 JSON（P0）

**复现**：向 UDP `5010` 发一帧 `{"alt":NaN,"ias":Infinity,...}`（等价于 `python tools/mock_export.py --nan`），再 `GET /state`。

**期望**：严格合法 JSON，无 `NaN`/`Infinity` 字面量，脏值被拒绝或清洗。

**实际**：`/state` 输出 `..."alt":NaN,"ias":Infinity...`，`json.loads(..., parse_constant)` 抛异常。
浏览器 `fetch("/state").json()` 会直接抛，面板状态行变成「连不上桥接」，整页冻结 —— 但桥接其实是好的。

**根因**：`tools/beacon.py` `TelemetryHub.feed()` 用默认 `json.loads`（Python 接受 `NaN`/`Infinity`），
`snapshot()` 又用默认 `json.dumps(allow_nan=True)` 输出。数字没做任何有限性检查。
`mock_export.py --nan` 这个注入开关本来就是用来验这条的，说明设计上要求「桥接拒绝脏数据」，实现却漏了。

---

## BUG-02 · 畸形慢变量打死 UDP 监听线程（P0）

**复现**：发 `{"sys":{"fuel":3200,"fuelx":"oops"}}`，随后继续发正常主帧。

**期望**：后续帧继续被接收，`stats.rx` 增长。

**实际**：控制台抛
```
ValueError: could not convert string to float: 'oops'
  beacon.py:351  total = float(fuel) + float(fuelx or 0)
```
线程退出，之后所有遥测都收不到，`/state` 永久冻结（rx 306 → 307，那 +1 是畸形包自己加的）。

**根因**：`fuelx` 未做类型检查就 `float()`；`udp_listener()` 里 `hub.feed(data)` 没有异常兜底，
一个坏包就能让整个遥测线程结束。任何脏数据（DCS 版本漂移、局域网串包）都能触发。

---

## BUG-03 · 命令文件单槽覆盖导致命令丢失（P0）

**复现**：连续 `POST /cmd` 发 `32:3007:1` 和 `35:3015:0`，同时让 Export.lua 按帧消费。

**期望**：两条都执行 `[3007, 3015]`。

**实际**：只有 `[3015]` 到达设备。

**根因**：`beacon.py` 每次 `/cmd` 都 `CMD_FILE.write_text(line)` 覆盖同一个文件；
`Export.lua` 每帧最多读一条并立刻删除。两条命令落在同一帧窗口内时，后一条把前一条盖掉。
真实场景：iPad 瞬动键的「按下 1 / 90ms 后松开 0」、连点两个按钮、两块设备同时操作，都会踩中。

---

## BUG-04 · 真实 DCS 结构下舵面偏度 / 起落架进度永远 null（P1）

**复现**：用真实探针结构（`Saved Games/DCS/Logs/dcsprobe.json`）驱动 `Export.lua`：
```
gear.nose.rod = 0
controlsurfaces.elevator = {left=0.0527655, right=0.0516842}
```

**期望**：`sys.gr≈0.75`、`sys.cs_e≈0.0527`。

**实际**：`gr=null, cs_e=null`（`cs_a/cs_r` 同理）。

**根因**：`dcs/Export.lua` 里
```lua
local function deepget(t, k1, k2)   -- 只支持两层
...
gr     = deepget(mech, "gear", "nose", "rod"),           -- 第 4 个参数被 Lua 忽略 → 取到 nose 表
cs_e   = deepget(mech, "controlsurfaces", "elevator"),   -- 取到 {left,right} 表
```
`numo()` 遇到 table 返回 `"null"`。单元测试夹具把这两处写成标量（`nose=0`、`elevator=0.012`），
所以 41 项单测全绿也没发现。**这是「夹具与真实结构不一致」掩盖的真实缺陷**：
面板的起落架进度条永远走 `frame.gear` 的 0/1 兜底，配平/舵面数据一直取不到。

---

## BUG-05 · `/cmd` 不校验数值，写出不可解析命令还返回 ok:1（P1）

**复现**：分别 POST `val=NaN` / `Inf` / `1e300` / `dev=-1`。

**期望**：400 拒绝，或写出 `Export.lua` 能解析的 `dev:cmd:val`。

**实际**：
```
200 {"ok":1}  文件 "32:3007:nan"
200 {"ok":1}  文件 "32:3007:inf"
200 {"ok":1}  文件 "32:3007:1e+300"
200 {"ok":1}  文件 "-1:3007:1"
```
`Export.lua` 的正则 `^(%d+):(%d+):(%-?[%d%.]+)$` 一个都匹配不上 → 回执 `fmt`，
iPad 一直停在「已发送 · 等回执…」，操作者以为按了没反应。

**根因**：`beacon.py` `do_POST /cmd` 只做 `int()/float()`，没有有限性、范围、符号校验；
`f"{val:g}"` 会产生 `nan`/`inf`/科学计数法；后端无法把失败反馈给调用方。

---

## BUG-06 · 屏幕回传把 DOWN_ 页面写进上半区（P1）

**复现**：注入 `sys.mfd = "C=UPPER_BASE,RTN,osb_txt_1,LOWER_BASE,sms_down_pilon_1"`。

**期望**：上半区保持 `UP_*` 或未同步；下半区记 `DOWN_*`。

**实际**：`mfdPage.center = "DOWN_MainMenu"`，上半区 33 个键标签全变「·」，按键全部失灵。

**根因**：`tools/panel.html::applyScreenText()` 把 `scoreSeg(upper)` 的结果直接赋给 `pid`，
没有像 `setPage()` / 旧状态清洗那样挡 `DOWN_`。`DOWN_MainMenu` 的指纹（`RTN` + `osb_txt_`）
在上半区 token 里偶然凑齐时就会赢过所有 UP 页。

---

## BUG-07 · MFD 按键回传的状态没持久化，且刷新会重放历史按键（P2）

**复现 A**：注入 `sys.bp="1:793"`（座舱按 D3），读 `localStorage["dcs-mfd-pages"]`。

**期望**：内存与存储都变成 `UP_MainMenu`。

**实际**：内存 `UP_MainMenu`，存储仍是 `UP_U1_RDR_AA`（`applyCockpitPresses` 改了 `mfdPage` 但没调 `savePages()`）。

**复现 B**：把 `bp` 设成有历史的高序号 `5:793,793,793,793,793`，手动选页 `UP_U3_TACAN` 后刷新。

**期望**：仍是 `UP_U3_TACAN`。

**实际**：变成 `UP_MainMenu`。`mfdSeq` 每次加载从 `0` 起算，新页面把 `bp` 里最后 8 次按键
**全部重放一遍**，覆盖掉用户刚选的页面。真实使用中每次刷新 iPad 页面都会跳页。

**根因**：`applyCockpitPresses()` 缺 `savePages()`；`mfdSeq` 没有「首包只对齐序号」的处理。
另外 `applyScreenText()` 里非当前屏的 `mfdLow` 变化也不触发 `touched`，同样不落盘。

---

## BUG-08 · 单元测试字段清单落后于 Export.lua（P2）

**复现**：`python tests/test_export_lua.py` → `40/41`，唯一失败：
`sys 字段完整且顺序稳定`，实际末尾多出 `ufcp`。

**根因**：2026-11-13 给 `encode_sys` 加了 UFCP 四窗文字回传（`sys.ufcp`），
`EXPECTED_SYS_FIELDS` 没同步。测试套件长期红着，等于失去回归价值。

---

## BUG-09 · `mfd-audit.py` 的 D3 被加了两次偏移（P2）

**复现**：读源码 `D3 = 2502 + 793`，而 `click(el)` 里又 `post(el + OFFSET)`。

**期望**：发出的命令号 3295（中屏 D3 = 元素 793 + 2502）。

**实际**：5797。审计脚本第一步「回主菜单」就打到了不存在的控件，后面 14 个页面的识别结果全不可信。

---

## BUG-10 · `check-panel.py` 溢出报告一触发就崩（P2）

**复现**：让任一 `.card` 横向溢出，执行脚本里的 `c.querySelector('h2').textContent`。

**期望**：报告出是哪张卡片溢出。

**实际**：`TypeError: Cannot read properties of null (reading 'textContent')`。
`panel.html` 的卡片标题是 `<h3>`（`.zone > h2` 是分区标题），没有 `h2`。
平时没溢出所以不炸，一旦真出排版事故，验收脚本反而自己先挂。

---

## BUG-11 · `vjoy_out.py` 心跳 URL 尾斜杠（P3）

`path = (u.path or "") + "/vjoy"`；`--report http://127.0.0.1:8080/` 会变成 `//vjoy` → 404，
`/input` 里 `vjoy.alive` 永远 false，手机显示「虚拟摇杆没起来」。默认 URL 不带斜杠，所以只在自定义配置时踩中。

---

## BUG-12 · 设备方法抛异常时仍报成功回执（P2）

**复现**：让 `GetDevice(32):performClickableAction` 抛异常，发一条命令，读 `sys.dbg`。

**期望**：`32:3007:X`（失败），页面显示「没执行」。

**实际**：`32:3007:D0`（成功）。

**根因**：`Export.lua::apply_command` 的兜底分支
```lua
local ok2 = pcall(function()
    local d0 = GetDevice(0)
    if d0 and d0.performClickableAction then d0:performClickableAction(cnum, vnum) end
end)
```
0 号设备没有该方法时函数体什么都不做，但 `pcall` 仍返回 true → 记成 `D0` 成功并累加 `ack_count`。
结果是「按了没反应，界面却说已执行」，排查方向被带偏。

---

## 修复记录（2026-11-13）

| ID | 改动文件 | 处理方式 | 验收 |
|---|---|---|---|
| BUG-01 | `tools/beacon.py` | `parse_constant` 拒绝 NaN/Infinity 字面量 + 递归非有限数检查 + 拒收脏帧 + 对外 `json.dumps(allow_nan=False)` | T-TLM-004 |
| BUG-02 | `tools/beacon.py` | `fuelx` 只认数字；`udp_listener` 给 `hub.feed` 包异常兜底并计坏包 | T-TLM-005 |
| BUG-03 | `tools/beacon.py` | 新增 `CMD_LOCK` + `write_cmd_file()`：写前等单槽被消费（≤0.3s），并发串行化 | T-CMD-006 |
| BUG-04 | `dcs/Export.lua` | 新增 `deepget3()` / `surface()`，兼容真实 `{left,right}` 与三级嵌套结构 | T-TLM-002b、单测 42/42 |
| BUG-05 | `tools/beacon.py` | `/cmd` 校验 dev/cmd 范围、val 有限且 ≤1e6；定点小数格式化，非法返回 400 | T-CMD-007 |
| BUG-06 | `tools/panel.html` | `applyScreenText` 把 `DOWN_` 结果挪到下半区，上半区只接受 `UP_`；非当前屏变化也落盘 | T-MFD-006 |
| BUG-07 | `tools/panel.html` | `applyCockpitPresses` 补 `savePages()`；`mfdSeq` 首包只对齐序号、不重放历史 | T-MFD-007 / 008 |
| BUG-08 | `tests/test_export_lua.py` | 期望清单补 `ufcp`，并新增一条字段存在性断言 | T-STAT-005 / T-REG-001 |
| BUG-09 | `tools/mfd-audit.py` | `D3 = 793`（元素号），注释写清 `click()` 会加 OFFSET | T-STAT-007 / T-MFD-012 |
| BUG-10 | `tools/check-panel.py` | 溢出去 `h3`；`#trimnote` 缺失不再误判 | T-STAT-008 / T-REG-002b |
| BUG-11 | `tools/vjoy_out.py` | `path = (u.path or "").rstrip("/") + "/vjoy"` | T-STAT-009 |
| BUG-12 | `dcs/Export.lua` | 兜底设备没有方法时主动 `error()`，让 `pcall` 返回 false → `:X` | T-CMD-010 |

**回归结果**：`66/82 通过，16 失败` → **`82/82 通过，0 失败`**；
`tests/test_export_lua.py` → **42/42 全绿**。详见 `docs/TEST-REPORT.md`。

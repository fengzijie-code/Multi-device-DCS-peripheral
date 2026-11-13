# 修改计划（依据 `docs/BUG-LIST.md`）

> 原则：**先修 P0 链路安全，再修数据正确性，再修状态机，最后修工具脚本**。
> 每一条都写清「改哪个文件、怎么改、由哪个用例验收」；全部改完后跑一遍完整回归。

---

## 1. 执行顺序与依赖

```
阶段 A（P0，桥接鲁棒性）  BUG-01 / BUG-02 / BUG-03 / BUG-05
        ↓  同一文件 beacon.py，一次改完，避免反复动路由
阶段 B（P1，Export.lua 数据正确性） BUG-04 / BUG-12
        ↓  需要重启 DCS 任务才生效（已在 HANDOFF 里写明）
阶段 C（P1/P2，面板状态机） BUG-06 / BUG-07
        ↓
阶段 D（P2/P3，测试与工具） BUG-08 / BUG-09 / BUG-10 / BUG-11
        ↓
全量回归：python tests/integration_test.py --report .tmp/integration-after.json
       + python tests/test_export_lua.py
```

**阶段 A 必须最先**：`/state` 现在会吐非法 JSON，会污染后面所有依赖面板的用例。

---

## 2. 逐条修改方案

### 阶段 A · `tools/beacon.py`

| Bug | 改法 |
|---|---|
| BUG-01 | ① `json.loads(..., parse_constant=...)` 让 `NaN/Infinity/-Infinity` 字面量直接抛异常；② 新增 `_nonfinite(obj)` 递归检查，任何非有限数一律拒收该帧（`_bad += 1`，保留上一帧）；③ 所有对外 `json.dumps` 加 `allow_nan=False`，兜底不再输出非法 JSON。 |
| BUG-02 | ① `feed()` 里 `fuelx` 先做数字类型判定再 `float()`，非数字按 0；② `udp_listener()` 给 `hub.feed(data)` 包 `try/except Exception`，异常只计坏包、不结束线程；③ `TelemetryHub` 增加 `note_bad()` 供监听线程计数。 |
| BUG-03 | 新增命令文件「槽位」写入：`CMD_LOCK` + `write_cmd_file(line)`。写之前等上一个文件被 Export.lua 消费掉（最多等 0.3s，正常 60Hz 下约 16ms），保证同一时刻文件里只有一条命令；多 iPad 并发也由锁串行化。**不改 `Export.lua`**，不需要重启 DCS 就能生效。DCS 没在跑时超时后覆盖并返回 `ok:0` 说明，不再谎报成功。 |
| BUG-05 | `/cmd` 校验：`dev`/`cmd` 必须是 `0..999999` 的整数，`val` 必须有限且 `abs(val) <= 1e6`；格式化改成不带指数的定点小数（`("%.4f" % val).rstrip("0").rstrip(".")`，去掉尾随点），保证一定匹配 `Export.lua` 的 `^%d+:%d+:%-?[%d%.]+$`。非法返回 `400 {"ok":0,"err":"..."}`。 |

**验收**：T-TLM-004 / T-TLM-005 / T-CMD-006 / T-CMD-007，另 T-CMD-001~005 不得回归。

### 阶段 B · `dcs/Export.lua`

| Bug | 改法 |
|---|---|
| BUG-04 | 新增两个取值助手：`deepget3(t,k1,k2,k3)` 下钻三层；`surface(v)` 兼容「裸标量 / `{value=…}` / `{left=…,right=…}`」三种形态（优先 `left`）。`gr` 用 `deepget3(mech,"gear","nose","rod")` 并兼容旧夹具的标量 `nose`；`cs_a/cs_e/cs_r` 用 `surface(deepget(mech,"controlsurfaces",...))`。真实探针结构由此能读到数值，旧单测夹具（标量）也仍然通过。 |
| BUG-12 | `apply_command` 的 0 号设备兜底改为：设备不存在或没有 `performClickableAction` 时主动 `error()`，让 `pcall` 返回 false → 记 `:X`，不再伪报 `D0`。 |

**验收**：T-TLM-002b / T-CMD-010；`tests/test_export_lua.py` 41 项不得回归。

### 阶段 C · `tools/panel.html`

| Bug | 改法 |
|---|---|
| BUG-06 | `applyScreenText()` 在写 `mfdPage` 之前加一道归一：若 `pid` 以 `DOWN_` 开头，把它挪到 `lowPid`（下半区），`pid` 置空；与 `setPage()` 里已有的防御保持一致。顺带把「非当前屏的 `mfdLow` 变化」也计入 `touched`，让所有屏的状态都能落盘。 |
| BUG-07 | ① `applyCockpitPresses()` 处理完 `fresh` 后调用 `savePages()`；② `mfdSeq` 初值改为 `null`，**首包只对齐序号、不重放历史按键**（`if (mfdSeq === null) { mfdSeq = seq; return; }`）。页面刷新时以 `sys.mfd` 屏幕回传和 localStorage 为准，不再把载入前发生的按键重演一遍。 |

**验收**：T-MFD-006 / T-MFD-007 / T-MFD-008；T-MFD-001~005、009~011 不得回归。

### 阶段 D · 测试与工具

| Bug | 文件 | 改法 |
|---|---|---|
| BUG-08 | `tests/test_export_lua.py` | `EXPECTED_SYS_FIELDS` 末尾补 `"ufcp"`，并补一条断言验证 UFCP 四窗文本字段存在。 |
| BUG-09 | `tools/mfd-audit.py` | `D3 = 793`（元素号，注释写清「click() 会自行加 OFFSET」），跑一次静态核对确认 3295。 |
| BUG-10 | `tools/check-panel.py` | 溢出报告改成 `c.querySelector('h3')?.textContent || '(card)'`，并去掉已不存在的 `#trimnote` 硬编码（改成可选、缺失不报错）。 |
| BUG-11 | `tools/vjoy_out.py` | `path = (u.path or "").rstrip("/") + "/vjoy"`。 |

**验收**：T-STAT-005/007/008/009、T-REG-001/002/002b、T-MFD-012。

---

## 3. 风险与约束

| 风险 | 处理 |
|---|---|
| 改 `Export.lua` 后真机要重启任务 | 在交付说明里显式提醒；本轮验证用嵌入式 Lua，已覆盖改动路径 |
| `write_cmd_file` 等槽位可能让 `/cmd` 最多阻塞 0.3s | 只在 DCS 没在收时发生；正常 60Hz 约 16ms，iPad 点击频率远低于此；不引入新线程 |
| 拒收含 NaN 的整帧会不会丢数据 | `Export.lua` 自身已把 NaN 清成 0 并打 `dirty`，正常链路不会产生 NaN；只有异常源才会被拒，且保留上一帧，比输出非法 JSON 安全 |
| `surface()` 优先 `left` 会不会和旧机型不一致 | 旧标量形态原样返回；`{left,right}` 才有分支，且真机左右差 < 5%，取 `left` 与既有 `rpm_l/temp_l` 口径一致 |
| 页面状态机改动影响 MFD 自动跟页 | `sys.mfd` 仍是权威来源；只挡 `DOWN_` 串区与历史重放，不改评分算法 |

---

## 4. 准出标准

1. `python tests/integration_test.py` → **0 失败**（82/82）。
2. `python tests/test_export_lua.py` → 全绿。
3. `tools/check-panel.py` 三视口无异常、console 干净。
4. `git diff` 只涉及上面列出的 7 个文件 + 4 份文档/脚本，无无关改动。
5. `docs/TEST-REPORT.md` 补上修复后数据，`docs/BUG-LIST.md` 状态全部改为「已修复」。

---

## 5. 执行状态（已完成）

| 阶段 | 状态 | 涉及文件 |
|---|---|---|
| A | ✅ 已完成 | `tools/beacon.py` |
| B | ✅ 已完成 | `dcs/Export.lua` |
| C | ✅ 已完成 | `tools/panel.html` |
| D | ✅ 已完成 | `tests/test_export_lua.py`、`tools/mfd-audit.py`、`tools/check-panel.py`、`tools/vjoy_out.py` |
| 全量回归 | ✅ 82/82 通过，0 失败 | `.tmp/integration-after.json` |

准出标准逐条核对：

1. ✅ `python tests/integration_test.py` → 82/82，0 失败。
2. ✅ `python tests/test_export_lua.py` → 42/42 全绿。
3. ✅ `tools/check-panel.py` 三视口无异常、console 干净（T-REG-002 / T-PANEL-009console）。
4. ✅ 变更仅涉及计划中的 7 个源文件 + 4 份新增文档 + 1 个新增测试脚本，无无关改动。
5. ✅ `docs/TEST-REPORT.md` 已补修复后数据；`docs/BUG-LIST.md` 12 条状态全部改为「已修复」。
6. ✅ **真机端到端已补做**：用户重启 `start-usb.bat` + DCS 任务后，
   `python tests/live_dcs_test.py --probe-version` → **11/11 通过**；
   版本自检确认 `Export.lua`（内存 + 磁盘）与 `beacon.py` 都是新版。见 `docs/TEST-REPORT-LIVE.md`。

**部署记录**：新版 `Export.lua` 已备份后部署到
`C:/Users/lenovo/Saved Games/DCS/Scripts/Export.lua`（备份 `Export.lua.bak-20261113-144040`）。
`dcs/Export.lua` 改动需要重启 DCS 任务生效、`beacon.py` 需要重启桥接生效 —— 这两步用户已完成并验证通过。

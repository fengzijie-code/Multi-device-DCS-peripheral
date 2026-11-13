# 当前实现 · 主动完整测试计划

> 版本 1.0 · 2026-11-13
> 与 `docs/TEST-PLAN.md`（2026-11-10 的路线图级方案）不同：本计划**只针对仓库里已经存在的代码**，
> 每一项都能在本机自动执行、自动判定，不依赖真 DCS、真 iPad、真 vJoy。
> 自动化脚本：`tests/integration_test.py`；执行结果：`docs/TEST-REPORT.md`。

---

## 1. 测试范围

### 1.1 被测对象（当前实际存在的东西）

| 层 | 文件 | 被测行为 |
|---|---|---|
| DCS 侧 | `dcs/Export.lua` | 60Hz 主帧、1Hz 慢变量包、MFD 按键扫描、指示器文字回传、命令文件反向通道、回执 |
| 桥接 | `tools/beacon.py` | HTTP 路由 `/ /panel /state /input /info /ping`、`POST /input /vjoy /cmd`、遥测汇聚、燃油斜率/续航、输入钳位/转发、命令文件写入 |
| iPad 页面 | `tools/panel.html` | 三栏仪表渲染、单位换算、冻结降级、10 个座舱按钮、MFD 三屏/页面状态机/33 键、UFCP 28 键+四窗文字 |
| vJoy 侧 | `tools/vjoy_out.py` | 按钮数、UDP 输入解析、心跳 URL（静态+单元级） |
| 模拟源 | `tools/mock_export.py` | 与 `Export.lua` 同线格式；NaN / 丢包 / 缺字段注入 |
| 工具链 | `tools/gen-mfd-pages.py`、`tools/mfd-pages.json`、`tools/check-panel.py`、`tools/mfd-audit.py`、`tools/replay.py`、`tools/watch-state.py` | 生成数据与面板一致、验收脚本自身可运行 |
| 已有单测 | `tests/test_export_lua.py` | 41 项断言回归 |
| Android | `android/app/src/main/java/.../*.kt` | **只做静态一致性核对**（按钮数、端点），本机无模拟器/真机，不跑 UI |

### 1.2 不在范围（明确排除，避免假覆盖）

- 真 DCS 实飞、真 iPad Safari、真机 vJoy 驱动、真实 Wi-Fi/热点链路延迟。
- `docs/TEST-PLAN.md` 里 P1+ 的 TLS/证书/QUIC/视频链路/性能压测 —— 代码里根本没实现，测了也是测空气。
- Android Compose UI 渲染与触控 —— 需要模拟器，本机不具备。

### 1.3 关键取舍：怎么算「模拟 iPad 输入」

用 **Chromium（系统 Chrome）+ 1024×768 / 768×1024 视口 + 触摸事件** 加载真实的 `/panel`，
在真实 DOM 上派发 `pointerdown` / `pointerup`（长按用真实的按住时长），
而不是直接拼 HTTP 请求。这样按钮的防误触、命令号换算、页面状态机都会真跑。
同时用 **真实 `dcs/Export.lua` 跑在嵌入 Lua 运行时**里接收命令文件并回写遥测，
形成闭环：

```
iPad DOM 点击 → POST /cmd → beacon 写 dcs_cmd.txt → Export.lua 每帧读取执行
   → Export.lua UDP 5010 发 sys/frame → beacon /state → iPad DOM 1Hz 刷新显示
```

`/input` 链（手机侧）用等价的 HTTP POST 直接模拟，因为手机摇杆不在本轮 iPad 输入范围内。

### 1.4 隔离要求（不许污染真实环境）

- `beacon.CMD_FILE` 与 Lua 侧 `USERPROFILE` 全部重定向到临时目录，**绝不写真实 `Saved Games`**。
- 桥接用独立端口（HTTP 8091 / UDP 5091），不碰 `start-usb.bat` 占用的 8080/5010。
- 测试结束关闭所有线程/浏览器、删除临时目录。

---

## 2. 要读取并校验的状态量（判据来源）

| 状态量 | 位置 | 意义 |
|---|---|---|
| `state.has_data` / `state.frame` | `GET /state` | 主帧是否新鲜、字段值 |
| `state.stats.{rx,bad,hz,age_ms}` | `GET /state` | 收包/坏包/频率/新鲜度 |
| `state.sys.*` | `GET /state` | 慢变量 30 项（`fuel` `gr` `ac` `radar` `wn` `wl` `cn` `ack` `acn` `dbg` `bp` `mfd` `ufcp`…）、`ff`、`endurance_s` |
| `state.sys_age_ms` | `GET /state` | 慢变量新鲜度 |
| `state.input.*` / `GET /input` | 桥接输入侧 | 轴、按钮位图、seq、转发开关、vJoy 心跳 |
| `dcs_cmd.txt` 内容 | 命令文件 | `dev:cmd:val` 是否完整正确 |
| Lua 侧设备动作记录 | 假 `GetDevice` | 哪条命令真的被执行、执行了几次 |
| DOM 文本 `#ias/#alt/#fuel/#gear/#mfdpage/...` | iPad 页面 | 数值换算、页面标题、按钮标签 |
| `document.body.className` / `#frozen` | iPad 页面 | 标签页、冻结态 |
| `localStorage["dcs-mfd-pages"]` | iPad 页面 | 页面状态持久化 |
| `console` / `pageerror` | iPad 页面 | JS 异常与资源错误 |

**所有断言必须同时给出期望值与实际值**，失败即记录为 bug 证据。

---

## 3. 测试项与预期结果

### S0 · 静态一致性（先跑， cheapest）

| ID | 输入 | 校验 | 预期结果 |
|---|---|---|---|
| T-STAT-001 | 读源码 | `beacon.MAX_BUTTONS` / `vjoy_out.MAX_BTN` / Kotlin `BUTTON_COUNT` | 三者都 = 30 |
| T-STAT-002 | 读源码 | `panel.CMD_OFFSET` / `mfd-audit.OFFSET` / `Export.lua` 命令号 | 全部 = 2502 |
| T-STAT-003 | 解析 `panel.html` 的 `MFD_PAGES` 块 | 与 `tools/mfd-pages.json` 逐键比较 | 57 页，键集与内容完全一致 |
| T-STAT-004 | 用 `gen-mfd-pages.py` 重生成到临时目录 | 与仓库内两份文件比对 | 输出零差异（生成器没有漂移） |
| T-STAT-005 | 解析 `Export.lua` `encode_sys` 字段 | 与 `tests/test_export_lua.py::EXPECTED_SYS_FIELDS` | 字段集与顺序完全一致 |
| T-STAT-006 | 读 `beacon.CMD_FILE` 与 `Export.lua CMD_FILE` | 归一化后的路径 | 同一个 `Saved Games/DCS/Logs/dcs_cmd.txt` |
| T-STAT-007 | 读 `mfd-audit.py` 的 `D3` | `click(el)` 会再加一次 `OFFSET` | `D3` 必须是**元素号**，不能是命令号 |

### S1 · HTTP 服务与路由

| ID | 输入 | 预期结果 |
|---|---|---|
| T-SVC-001 | `GET /ping` | 200 JSON，含 `server_ms/uptime_s/peer` |
| T-SVC-002 | `GET /`、`/panel`、`/panel.html`、`/panel/` | 都 200 且是面板/自检 HTML（尾斜杠归一化生效） |
| T-SVC-003 | `GET /nope` | 404，且正文列出 `/panel`、`/state` |
| T-SVC-004 | `GET /input` | 200，含 `axes/buttons/seq/forwarding/vjoy` |
| T-SVC-005 | `GET /info` | 200 JSON，含 `ipv4/ipv6/uptime_s` |
| T-SVC-006 | `POST /bogus`、空 body、坏 JSON、>4KB | 分别 404 / 413 / 400 / 413，且不写命令文件 |
| T-SVC-007 | `GET /state` 在无数据时 | `has_data=false`、`frame=null`、`sys=null`，仍是合法 JSON |

### S2 · 遥测链路（`Export.lua` → UDP → `/state`）

| ID | 输入 | 校验 / 预期结果 |
|---|---|---|
| T-TLM-001 | 真实 `Export.lua` 以 60Hz 推进模型时间 1 秒 | `has_data=true`，`frame` 22 字段齐全且顺序稳定，`stats.hz≈60`，`age_ms<2000`，`bad=0` |
| T-TLM-002 | 同上，1Hz 慢变量包 | `sys` 含 `ack/acn/dbg/bp/mfd/ufcp` 等全部字段，`sys_age_ms<5000` |
| T-TLM-003 | 燃油按 1.15 kg/s 下降 | `sys.ff≈-4140 kg/h`，`endurance_s` 与剩余油量/流量自洽 |
| T-TLM-004 | 主帧注入 `NaN` / `Inf`（`mock_export.py --nan` 等价） | `/state` **必须是严格合法 JSON**，不含 `NaN`/`Infinity` 字面量；数值被拒绝或清洗，绝不透传 |
| T-TLM-005 | 慢变量 `fuelx` 给非数字字符串 | UDP 监听线程不能死：继续发包后 `stats.rx` 仍增长、`has_data=true` |
| T-TLM-006 | 主帧停 2 秒 | `has_data=false`、`frame=null`、页面红条「数据已冻结」可见 |
| T-TLM-007 | 慢变量停 5 秒（主帧继续） | `sys=null`、`sys_age_ms` 递增、状态行提示「没有慢变量」 |
| T-TLM-008 | 恢复两路发包 | `has_data` 与 `sys` 都恢复 |
| T-TLM-009 | 切换成 TF-51D 形态（多数字段 `null`、燃油比例） | `null` 原样保留，面板显示 `--` 而不是 `0` |
| T-TLM-010 | 发一条畸形 UTF-8 / 非对象 JSON | `stats.bad` +1，服务不崩 |

### S3 · iPad 仪表显示（真实 DOM）

| ID | 输入 | 预期结果 |
|---|---|---|
| T-PANEL-001 | 有数据 + JF-17 | 顶部 `在线 · 遥测 … Hz`、机型 `JF-17`、绿点 |
| T-PANEL-002 | `ias=155 m/s, alt=8000 m, agl=7400 m, vs=2.25, hdg=1.2345, g=1.02, mach=0.42` | `301 kt / 26247 ft / 24278 ft / 443 fpm / 71° / 1.0 g / 0.42` |
| T-PANEL-003 | 燃油 kg 口径 | `fuel` 显示 kg、`ff` 显示 kg/h、油量条按 `total/fuelMax` |
| T-PANEL-004 | 燃油比例口径 | 单位变 `%`、`%/h`，读数保留 1 位小数 |
| T-PANEL-005 | `gear=1/flaps=0.3/sbrk=0/wbrake=0.25/canopy=1` | 「放下 / 30% / 0% / 刹车 / 打开」 |
| T-PANEL-006 | 战斗区 `wn/wc/cn/wl/radar` | 弹种、余量、机炮、挂载清单、雷达「开」 |
| T-PANEL-007 | 慢变量全 `null` | 对应位置显示 `--`，不出现假 0 |
| T-PANEL-008 | 冻结态 | `#frozen` 可见、`body.frozen` 存在、卡片半透明 |
| T-PANEL-009 | 1024×768 / 768×1024 两个视口 | 无横向溢出、console / pageerror 为空 |
| T-PANEL-010 | 点三个标签 | 仪表/MFD/UFCP 视图互斥可见 |

### S4 · iPad 座舱反向控制（真实长按 + 回执闭环）

| ID | 输入 | 预期结果 |
|---|---|---|
| T-CMD-001 | 按住「起落架 放」≥500ms | 命令文件 `32:3007:-1`；Lua 侧设备收到；`frame.gear→1`；DOM 变「放下」 |
| T-CMD-002 | 按住同按钮 <500ms 就松开 | 不写命令文件、设备动作计数不变 |
| T-CMD-003 | 点「襟翼 放下」(`data-hold=0`) | 立即发 `35:3015:1`，无需长按 |
| T-CMD-004 | 逐个触发 10 个座舱按钮 | 每条 `(dev, el+2502, val)` 与 `data-*` 完全一致 |
| T-CMD-005 | 成功回执 `dbg="32:3007:D"` 且 `acn` 递增 | `#mfdack` 显示「已执行」；`N/M/X` 显示「没执行」 |
| T-CMD-006 | 同一帧内连发两条不同命令 | 两条都到达 Lua 设备（命令不能互相覆盖丢失） |
| T-CMD-007 | `val=NaN` / `Inf` / `1e300` / 负 dev / 负 cmd | 桥接拒绝（400）或输出可被 `Export.lua` 解析的行；不得产生 `nan`/`inf`/`e+` 这类无法解析的命令文件，且不能谎报 `ok:1` |
| T-CMD-008 | 缺 `dev` / 缺 `cmd` / 非法 JSON | 400，不写命令文件 |
| T-CMD-009 | `dev` 号不存在 | Lua 回执 `:N`，页面显示「没执行」 |

### S5 · MFD / UFCP 状态机

| ID | 输入 | 预期结果 |
|---|---|---|
| T-MFD-001 | 点左/中/右 MFD | `#mfdsel` 与按键元素号基准切换正确（734/767/800），三屏各自独立 |
| T-MFD-002 | 主菜单按 `D3` / `D2` / `D4` | 分别回主菜单 / 按屏快切 CMBT·雷达·HSD / SMS·无·CLINK |
| T-MFD-003 | 切到雷达页 | 键标签变成 `L3 60`、`L5 4BR`、`U5 CNTL` |
| T-MFD-004 | 点瞬动键 / 长按 PWR | 瞬动键发 `1` 再发 `0`；PWR 需 600ms 且只发 `±1`（不发 0） |
| T-MFD-005 | 注入 `sys.mfd` 主菜单 / 雷达页 / 上下半区元素名 | 页面自动识别正确，上半区与下半区互不串 |
| T-MFD-006 | 注入会让 `DOWN_` 页在**上半区**得分最高的回传 | 上半区状态绝不能被写成 `DOWN_*`（否则上半区按键全失灵） |
| T-MFD-007 | 注入 `sys.bp` 座舱按键 | 页面跟随跳转，且写入 `localStorage` |
| T-MFD-008 | 下拉框改页后刷新页面 | 页面状态保留 |
| T-MFD-009 | 注入 `sys.ufcp="A|B|C|D"` 并切到 UFCP | 四个液晶窗分别显示 A/B/C/D |
| T-MFD-010 | UFCP 功能键点击 | `dev=46`、`cmd=el+2502`、瞬动 1→0 |
| T-MFD-011 | 点「刷新」 | 立即重新拉 `/state` 并强制同步一次 |
| T-MFD-012 | `mfd-audit.py` 的 `D3` | 实际发出的命令号 = 3295（不是 5797） |

### S6 · 输入链（手机侧，`/input`）

| ID | 输入 | 预期结果 |
|---|---|---|
| T-IN-001 | `POST /input {x:0.5,y:-0.25,r:0,t:0.7,vx:1,vy:-1,b:5}` | `/input` 快照一致、`seq` 递增、UDP 转发载荷一致 |
| T-IN-002 | 不带 `t` | `axes.t=null`，转发载荷里没有 `t`（油门保持） |
| T-IN-003 | `NaN`/`Inf`/`±99`/非数字 | 全部钳到合法范围，无 NaN 透传 |
| T-IN-004 | `POST /vjoy {"ok":true}` | `/input.vjoy.alive=true`、`ok=true` |
| T-IN-005 | `b` 超过 30 位 | 位图截断到 30 位，不越界 |

### S7 · 既有测试与工具回归

| ID | 输入 | 预期结果 |
|---|---|---|
| T-REG-001 | `python tests/test_export_lua.py` | 全绿（0 失败） |
| T-REG-002 | `python tools/check-panel.py <测试URL> .tmp` | 三视口都完成、无异常、`console` 干净 |
| T-REG-003 | `mock_export.py --aircraft tf51` / `--nan` 短时间运行 | 进程正常退出，不崩 |
| T-REG-004 | `replay.py --file <现有 jsonl> --speed 50 --quiet` | 能加载并重放，不抛异常 |

---

## 4. 执行顺序

严格按编号推进，前一组不通过也继续跑完（避免一个失败掩盖后面的问题），但记录受阻项：

```
S0 静态一致性
  ↓（确认测的是当前代码，且生成器/页面数据没漂移）
S1 起服务 + 路由（此时无遥测）
  ↓
S2 起 Export.lua 模拟源，验证 /state 全链路与降级
  ↓
S3 起浏览器，验证 iPad 渲染（依赖 S2 有数据）
  ↓
S4 真实点击 → 命令闭环（依赖 S2/S3）
  ↓
S5 MFD/UFCP 状态机（依赖 S4 的命令通道）
  ↓
S6 输入链（独立，可在任意时刻补跑）
  ↓
S7 跑既有脚本回归
  ↓
汇总 → docs/TEST-REPORT.md → docs/BUG-LIST.md → docs/FIX-PLAN.md → 修复 → 全量回归
```

**为什么 S4 放在 S3 之后**：反向控制的最终判据是「iPad 上的读数跟着变」，必须先证明渲染是对的，
否则分不清是命令没生效还是显示没刷新。

---

## 5. 判定与记录

- 每项输出 `[PASS]` / `[FAIL]` + 期望值 + 实际值；失败项自动归入 bug 清单，按以下分级：
  - **P0 阻断**：链路断、命令丢失/错发、服务被脏数据打死、非法 JSON 输出。
  - **P1 严重**：功能不可用、状态量错误、防误触失效、页面状态串区。
  - **P2 一般**：体验/提示/持久化/工具脚本错误。
  - **P3 轻微**：文案、死代码、文档与实现不一致。
- 每条 bug 必须带：复现步骤、期望、实际、证据（状态量片段/日志）、根因定位（文件+行）。
- 修复后**重跑同一套脚本**，输出「修复前 N 项失败 → 修复后 0 项失败」的对比。

---

## 6. 交付物

| 文件 | 内容 |
|---|---|
| `docs/TEST-PLAN-CURRENT.md` | 本计划 |
| `tests/integration_test.py` | 自动化执行脚本（可重复运行） |
| `docs/TEST-REPORT.md` | 逐项执行结果（修复前 / 修复后两轮） |
| `docs/BUG-LIST.md` | bug 清单 |
| `docs/FIX-PLAN.md` | 修改计划与执行状态 |

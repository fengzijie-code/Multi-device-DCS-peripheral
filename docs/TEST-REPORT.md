# 当前实现 · 测试执行报告

> 自动化脚本：`tests/integration_test.py`
> 计划：`docs/TEST-PLAN-CURRENT.md` ｜ bug 清单：`docs/BUG-LIST.md` ｜ 修改计划：`docs/FIX-PLAN.md`
> 原始明细：`.tmp/integration-before.json`（修复前）、`.tmp/integration-after.json`（修复后）

---

## 1. 执行环境（全部隔离，未碰生产）

| 项 | 值 |
|---|---|
| 桥接 | `beacon.py` 进程内启动，HTTP `127.0.0.1:8091`、遥测 UDP `5091`、输入转发 UDP `5092` |
| DCS 侧 | **真实 `dcs/Export.lua`** 跑在 lupa Lua 运行时里，假 `LoGet*` / `GetDevice` / `list_indication`；结构严格照真实探针 `dcsprobe.json`（`gear.nose.rod`、`controlsurfaces.elevator={left,right}`） |
| iPad 侧 | 系统 Chrome 157，Playwright `1024×768` / `768×1024`，真实 `pointerdown/pointerup` 与 500/600ms 长按 |
| 命令文件 | 重定向到 `%TEMP%/dcs-it-*/Saved Games/DCS/Logs/dcs_cmd.txt`，**没有写真实 Saved Games** |
| 生产端口 | 8080 / 5010 / 5011 全程未被占用或写入 |

闭环证据：`T-CMD-001a/b/c` 一次「起落架 放」从 DOM 长按 → `32:3007:-1` → Lua 设备执行 → `frame.gear=1` → iPad 显示「放下」，全链路通。

---

## 2. 第一轮（修复前）结果

```
66/82 通过，16 失败
```

| 组 | 通过 | 失败 | 结论 |
|---|---|---|---|
| S0 静态一致性 | 4 | 4 | 4 个工具/单测自身缺陷 |
| S1 HTTP 服务与路由 | 10 | 0 | 路由、异常请求、404 提示全部正确 |
| S2 遥测链路 | 6 | 4 | 主帧/慢变量/降级正常；NaN、畸形包、`cs_*`/`gr` 有问题 |
| S3 iPad 仪表显示 | 9 | 0 | 单位换算、两种油量口径、冻结、双视口、console 全通过 |
| S4 座舱反向控制 | 9 | 3 | 防误触、映射、回执正常；命令丢失、非法值、假回执有问题 |
| S5 MFD/UFCP | 9 | 3 | 键位/标签/瞬动/屏幕识别/UFCP 正常；上半区串页、持久化有问题 |
| S6 输入链 | 5 | 0 | 钳位、油门保持、心跳、按钮位图全通过 |
| S7 既有脚本回归 | 3 | 2 | `check-panel.py`/`mock_export.py`/`replay.py` 能跑；单测红、audit 命令号错 |

失败项（16）：

| ID | 级别 | 期望 | 实际 |
|---|---|---|---|
| T-STAT-005 | P2 | 单测 sys 字段清单 = Export.lua 28 字段 | 27 个，缺 `ufcp` |
| T-STAT-007 | P2 | `mfd-audit.py` D3 → 3295 | 5797（双重偏移） |
| T-STAT-008 | P2 | 验收脚本取 `.card` 内真实标题 | 取 `h2`，`.card` 里只有 `h3` |
| T-STAT-009 | P3 | 心跳 URL 尾斜杠归一 | `(u.path or "") + "/vjoy"` → `//vjoy` |
| T-TLM-002b | P1 | `cs_e≈0.0527`、`gr≈0.75` | 都是 `null` |
| T-TLM-004 | P0 | `/state` 是严格合法 JSON | 输出 `NaN` / `Infinity` 字面量 |
| T-TLM-005 | P0 | 畸形慢变量后继续收包 | `ValueError` 打死 UDP 监听线程，rx 只 +1 |
| T-CMD-006 | P0 | 两条命令都执行 `[3007,3015]` | 只有 `[3015]`，前一条被覆盖 |
| T-CMD-007 | P1 | 非法 val 被拒或可解析 | 写出 `nan` / `inf` / `1e+300` / `-1:…` 且返回 `ok:1` |
| T-CMD-010 | P2 | 设备方法抛异常时不报成功 | 回执 `32:3007:D0`（假成功） |
| T-MFD-006 | P1 | 上半区状态不是 `DOWN_*` | 被写成 `DOWN_MainMenu` |
| T-MFD-007 | P2 | 座舱按键跳页写入 localStorage | 内存变了、存储没变 |
| T-MFD-008 | P2 | 刷新后保留且不重放旧按键 | 变成 `UP_MainMenu` |
| T-REG-002b | P2 | 溢出报告不抛异常 | `TypeError: … reading 'textContent'` |
| T-REG-001 | P2 | `test_export_lua.py` 退出码 0 | rc=1，1 项失败 |
| T-MFD-012 | P2 | audit D3 命令号 3295 | 5797 |

**测试台自身修正（不算 bug）**：首轮曾出现 `hz=1668`（60 帧瞬间灌入）、`ff=None`（燃油样本无墙钟跨度）、`T-PANEL-001=没有数据`（浏览器启动期间主帧过期）、`T-TLM-003 ff=-3733` 容差过窄 —— 分别改为按 60Hz 墙钟节奏推进、1 秒一包、20Hz 主帧心跳、斜率容差按墙钟抖动放宽。修正后这四项均为 PASS。

---

## 3. 第二轮（修复后）结果

按 `docs/FIX-PLAN.md` A→B→C→D 全阶段执行完毕后，同一套脚本原样重跑：

```
82/82 通过，0 失败
```

| 轮次 | 通过 | 失败 | 明细 |
|---|---|---|---|
| 修复前 | 66/82 | 16 | `.tmp/integration-before.json` |
| 修复后 | **82/82** | **0** | `.tmp/integration-after.json` |

修复前 16 个失败项逐项转绿：

| 失败项 | 修复后 |
|---|---|
| T-STAT-005 / T-REG-001 | PASS（单测 `EXPECTED_SYS_FIELDS` 补 `ufcp`，42/42） |
| T-STAT-007 / T-MFD-012 | PASS（audit D3 改为元素号 793 → cmd 3295） |
| T-STAT-008 / T-REG-002b | PASS（验收脚本改取 `h3`） |
| T-STAT-009 | PASS（心跳 URL `rstrip("/")`） |
| T-TLM-002b | PASS（`gr`/`cs_*` 按真实结构下钻，实测 0.75 / 0.0527） |
| T-TLM-004 | PASS（脏帧拒收，`/state` 严格合法 JSON） |
| T-TLM-005 | PASS（畸形 `fuelx` 不再打死监听线程） |
| T-CMD-006 | PASS（两条命令都执行 `[3007,3015]`） |
| T-CMD-007 | PASS（NaN/Inf/1e300/负 dev 一律 400） |
| T-CMD-010 | PASS（失败回执改 `:X`，不再伪报 `:D0`） |
| T-MFD-006 | PASS（上半区不再被写成 `DOWN_MainMenu`） |
| T-MFD-007 | PASS（座舱按键跳页写入 localStorage） |
| T-MFD-008 | PASS（刷新保留页面、不重放历史按键） |

补充验证：`python tests/test_export_lua.py` → **42/42 全绿**；
`tools/check-panel.py` 三视口验收、`mock_export.py --nan/--aircraft tf51`、`replay.py` 回放全部无异常。

> ⚠️ 本轮修改了 `dcs/Export.lua`（BUG-04 / BUG-12）。真机上必须**重启 DCS 任务**才会生效；
> `beacon.py` 与 `panel.html` 的改动分别重启桥接 / 刷新浏览器即可。

---

## 4. 真机补充验证（14:39，用户开启真 DCS 任务后）

离线闭环之后，又在**真 DCS / 真 8080 桥接**上跑了一次「虚拟输入 → 状态输出对应」测试，
脚本 `tests/live_dcs_test.py`，报告 `docs/TEST-REPORT-LIVE.md`。

结果 **10/11 通过**：只读探针（读参数 / 设备扫描 / 40 参数快照 / 不存在设备）、
MFD 页面切换（D3 回主菜单 → U1 进雷达模式菜单 → D3 回主菜单，且 `sys.bp` 序号跟随）、
UFCP 键回执（`46:3202:D`、`acn` 递增）全部在真机上对得上。唯一未达预期的是
`sys.gr/cs_*` 为 `null` —— 原因是**当时 DCS 加载的是旧版 Export.lua、8080 也是修改前的 beacon.py**，
不是新修复失效。

用 DCS 自带 probe 通道取得真机结构证据：`gear.nose` 是 table（`.rod=0`）、
`cs.elevator` 是 table（`.left=0.003027`），正好坐实 BUG-04 的根因与新修法。

新版 `Export.lua` 已备份后部署到 `Saved Games/DCS/Scripts/`（与仓库 sha1 一致）。
用户随后重启了 `start-usb.bat` 与 DCS 任务（14:44），**14:45 重跑真机测试：11/11 全部通过**。
版本自检确认三处都是新版：`sys.gr=0.0` / `sys.cs_e` 有实时数值（旧版恒 null）、
部署文件与仓库逐字节一致、`POST /cmd val=NaN` 返回 `400 {"ok":0,"err":"out of range"}` 且 `sys.dbg` 不再变 `fmt`。
完整报告见 `docs/TEST-REPORT-LIVE.md`（含版本自检、真机结构证据、两轮对比）。

| 轮次 | 离线回归 | 单测 | 真机虚拟输入→状态输出 |
|---|---|---|---|
| 修复前 | 66/82 | 40/41 | 10/11（旧版组件） |
| 修复后 + 重启 | **82/82** | **42/42** | **11/11** |

## 5. 功能语义层：尚未真机执行（14:51 追问后补的能力普查）

用户追问「雷达模式/返回/状态检测准确性、塔康输入、航路点、无线电频率、武器选择都测了吗」——
**答案是：此前一项都没测**，前四节测的都是链路层。详见 `docs/TEST-PLAN-FEATURES.md`。

已补做的、不依赖 DCS 的部分：

- **状态检测准确性全量测试** `tests/mfd_recognition_test.py`（复刻面板打分算法）：
  57 页自识别 **12 正确 / 4 认错 / 41 认不出 / 0 串区**；
  认错的 4 页是雷达 CNTL 浮层、SMS AG/AA、BIT；DATA 全系准确率 0/11。
  结论：TACAN / DATA / SMS 子页等 41 页 DCS 不导出元素名指纹，**只能靠按键推演 + 下拉框手选**，
  这是准确性的真实上限。
- **接口能力普查**：`LoGetRadarInfo` 不存在、`LoGetNavigationInfo=nil`、目标信息全 nil；
  可读的只有 `SelfData.Flags.RadarActive`、`PayloadInfo.CurrentStation/Stations`、UFCP 四窗文本。
  因此雷达模式、塔康频道数值、无线电真实频率、航路点数值**无法做输入→状态闭环验证**。
- **真机功能层已执行**（18:48 用户重启任务+USB 后）：`python tests/live_features_test.py --allow-input`
  → **VERIFY 5/5 通过**，另有 5 项 INDIRECT、3 项 LIMIT、1 项 SKIP，共 14 项。
  报告 `docs/TEST-REPORT-FEATURES.md`。

  最有价值的输入→状态对应：UFCP `DST/4` → 四窗从 `FP-A 01|CAS MAN||001 001`
  变成 `DST 00|431718 N|0402112E|+ 06556`（含经纬高），`RTN` 正确复原；
  中屏 U1 弹 10 个雷达模式项、L1 返回、D3 回主菜单，`sys.bp` 序号全程跟随。

  两处首轮「失败」已定性为**测试设计问题、非产品缺陷**：电台步进需先选中参数且 3 秒内拨动
  （按键到达编辑态但波道号未变，已降级 INDIRECT）；武器选择因本任务 7 挂点全 `x0` 无挂载
  无法验证（已改 SKIP，`/input` 链路本身通）。详见 `docs/TEST-PLAN-FEATURES.md` 第 4 节。

| 层级 | 修复前 | 修复后 / 重启后 |
|---|---|---|
| 离线闭环 `integration_test.py` | 66/82 | **82/82** |
| Export.lua 单测 | 40/41 | **42/42** |
| 真机链路层 `live_dcs_test.py` | 10/11（旧版组件） | **11/11** |
| 真机功能层 `live_features_test.py` | 未测 | **VERIFY 5/5**（14 项分级） |

## 6. 复现命令

```bash
# 离线完整回归（约 1 分钟，自动起隔离环境、自动清理，不需要 DCS）
python tests/integration_test.py

# 单独跑 Export.lua 单测
python tests/test_export_lua.py

# 真机链路层验证（需要 DCS 在任务里 + 8080 桥接活着）
python tests/live_dcs_test.py --probe-version

# 真机功能语义层验证（同样需要在座舱里）
python tests/live_features_test.py
python tests/live_features_test.py --allow-input     # 额外测武器切换

# MFD 页面识别准确性（纯离线，不需要 DCS）
python tests/mfd_recognition_test.py
```

---

## 7. 手机端战斗页补脚舵 / 视角（20:15）

用户指出战斗页两个问题：**没有脚舵、不能转视角**。定位结果：

- 脚舵：`YokeController` 每帧都在算 `rPos`（滑块优先、否则「拧手机」）并发送，
  但 `CombatScreen` 没有 `RudderBar`，屏幕上没有可压住的入口。
- 视角：`viewX/viewY` 只能由 `setView()` 写入，而 `MainActivity` 只把 `onView`
  传给了 `YokeScreen`；战斗页既没有 `ViewPad` 也没接回调 → `vx/vy` 恒 **0**。
- `docs/YOKE.md` 原写「战斗页只留交战要用的」，属于刻意取舍，不是漏写。

改动（右列盲操按钮一个都没挪）：

| 文件 | 改动 |
|---|---|
| `android/.../ui/CombatScreen.kt` | 中间列改成「杆位（`BoxWithConstraints` 自适应尺寸）+ 脚舵滑块 + 视角区」；新增 4 个回调参数；复用 `RudderBar`/`ViewPad`，死区/反转/横纵互换全部沿用起降页 |
| `android/.../MainActivity.kt` | 给 `CombatScreen` 接上 `onRudder`/`onRudderRelease`/`onView`/`onViewRelease` |
| `docs/YOKE.md`、`docs/HANDOFF.md` | 战斗页说明与能力表同步 |
| `tests/integration_test.py` | 新增 **T-STAT-010**：静态守住四个回调 + 两个控件，防止再退化 |

验证：

- `gradlew :app:compileDebugKotlin --offline` → **BUILD SUCCESSFUL**（JBR OpenJDK 25 / Gradle 9.9.0）
- `gradlew :app:assembleDebug --offline` → **BUILD SUCCESSFUL**，
  APK `android/app/build/outputs/apk/debug/app-debug.apk`（11.9 MB，20:15）
- 全量离线回归 → **83/83 通过，0 失败**（比之前多一项 T-STAT-010）
- 42/42 单测、11/11 真机链路、功能层 VERIFY 5/5 均未受影响

### 真机触屏验证（20:17，Pixel 6a USB 已连）

用户把 Pixel 用 USB 接上后，`python tools/install-apk.py` 装好新 APK
（设备 `35311JEGR07ZVC`，`adb reverse tcp:8080` 隧道已在），
用 `adb shell input tap/swipe` 打真实触摸，PC 侧轮询 `/input` 校验：

| 操作 | 读到的状态量 | 判定 |
|---|---|---|
| 战斗页截图 | 中间列出现「脚舵」滑块 + 「视角 按住拖动」区，右列按钮位置不变、无溢出 | ✅ |
| 校准页点「校零」→ 战斗页点「解锁」 | 按钮变「已解锁 · 点此上锁」 | ✅ |
| 脚舵滑块按住左→右拖 1.5s | `r` 连续 0.12→0.43、**峰值 0.729**；期间 `vx/vy` 恒 0 | ✅ |
| 视角区按住拖到右上 1.5s | `vx=1.0`、`vy=0.833`；期间 `r` 恒 0 | ✅ |
| 松手 | `r=0, vx=0, vy=0`（回中） | ✅ |
| 收尾点「上锁」 | 按钮变回「点击解锁」，`/input.axes` 全 0 | ✅ |

**两路互不串扰**，这正是本次修复要验证的对应关系。截图证据 `.tmp/pixel-combat0.png`。

#### 微调（20:25）：视角区改正方形

用户反馈「视角太大，跟绿点指示一致就行」。原来 `ViewPad` 是
`fillMaxWidth().height(96.dp)` 的扁宽横条，里面的圆形底盘指示只占中间一小块。
改成 **96dp 正方形居中**（外面套 `Box` 保持这一行高度），圆正好内切容器。
映射半径仍是 `min(宽,高)/2-10 = 38dp`，**手感完全不变**。

重新编译 / 打包 / 安装后复验：截图确认小方块居中、脚舵条与右列按钮无重叠；
触摸拖 100px / 80px 得到 `vx=0.847`、`vy=0.678`（正好 100/116、80/116），
松手全回中，收尾上锁。截图 `.tmp/pixel-viewpad-square.png`。

> 视角在 DCS 里仍要绑 **Absolute** 相机水平/垂直轴，见 `docs/BINDING.md`。
> 这次只验证到「手机 → 桥接 → vJoy 输入」这一跳；DCS 里视角/脚舵实际动没动，
> 还要在座舱里肉眼确认（本次 PC 侧 `has_data=false`，DCS 不在任务里）。

---

## 8. 战斗页重排 + 机炮/投放拆键（20:50，20:53 / 20:57 两次更正）

原始要求：「视角放左上角，下面放发射，发射分左右两个键（机炮和武器），脚舵最底下；
绿点指示不要独占一横行，贴在油门右侧；雷达、武器、干扰弹等放到绿点旁边 / 中间剩余空间。」

- **20:53 更正**：「我说错了，是把武器、机炮、和视角都放在右上角」→ 视角 + 两个发射键
  当成一整组镜像到最右列顶部，绿点盘留在油门右侧，中间按钮区不变。
- **20:57 更正**：「校准，还有剩下的在中间的那 4 个太大了。你都得改小一点」→
  中间顶部的「校零 / 解锁」按钮和武器↑↓ / 锁定 / 干扰弹四个按钮全部收成固定小尺寸、
  2×2 居中，不再用 `weight(1f)` 撑满半屏。

**以下记录的是最终版（右上角 + 紧凑中间组 + 21:14 放大右上角三个控件）。**

### 按键 markdown 核查结果

`docs/BINDING.md` 原本**只有一个发射键**：

```md
| **BTN7** | `FIRE = 6` | 发射 | 战斗页 · 发射（最下，红） | `Trigger` / `Release` / `Fire` | 已有 |
```

`Trigger`（机炮扳机）和 `Weapon Release`（挂架投放 / Pickle）在 DCS 里是**两条独立命令**，
一个按钮只能绑一条，旧写法确实把两者混了。按「不重排已有编号」原则：

| vJoy | 常量 | 语义 | DCS 里绑 |
|---|---|---|---|
| `JOY_BTN7` | `FIRE = 6` | **武器投放**（原「发射」，语义收窄） | `Weapon Release` / `Pickle` / `Bomb Release` |
| `JOY_BTN12` | `GUN_FIRE = 11` | **机炮**（新增） | `Gun` / `Cannon` / `Trigger` / `Weapon Fire` |

7–9 的预留位（`RESERVED_TWS` / `TARGET_PREV` / `TARGET_NEXT`）**没动**。
`BINDING.md` 补了迁移步骤：vJoy 按钮数 ≥ 12 → 重启 DCS → 把原来绑在 `BTN7` 的
Trigger 改绑 `BTN12` → `BTN7` 改绑 Weapon Release。`YOKE.md` / `LAYOUT.md` 同步。

### 最终版面

| 位置 | 放什么 |
|---|---|
| 最左全高 | 油门竖条 |
| 紧贴油门右侧 | 绿点盘 `StickPad`，`BoxWithConstraints` 自适应 ≤140dp，只看不碰 |
| 中间（垂直居中） | 解锁键 220×42dp + 武器↑/↓、锁定、干扰弹各 132×60dp 的 2×2 紧凑组 |
| **右上角**（列宽 220dp） | `ViewPad` **160dp 正方形**，`Alignment.CenterEnd` 靠右边缘，标签 13sp |
| **右上角 · 视角正下方** | 左「机炮」/ 右「武器」两个红色 `GuardButton`，**84dp 高、18/12sp 文字**，各 250ms 长按 |
| 中间留白处底部 | 一行只读状态字（链路 ms / Hz / vJoy） |
| 最底下 | `RudderBar` 跨整宽 |

旧版 `ViewPad` 是 `fillMaxWidth().height(96.dp)` —— 96dp 方块独占一整行、两侧全空；
`StickPad` 用 `weight(1f)` 独占中间一大块；中间 4 个按钮又各撑到约 300×130dp。
横屏只有约 411dp 高，这三处是主要浪费。为此给共享的 `ArmButton` 加了可选
`modifier` / `height` 参数（默认 46dp 不变，起降页尺寸不受影响）。

### 真机验证（Pixel 6a，`35311JEGR07ZVC`，USB 隧道在）

四个版本都各自 `assembleDebug --offline` BUILD SUCCESSFUL（15–26s）→ `install-apk.py`
装机 → 截图 → `uiautomator dump` 取坐标 → 真实触摸 + PC 侧 20ms 轮询 `/input`：

| 版本 | 截图 | 版面 |
|---|---|---|
| 20:50 左上角版 | `.tmp/pixel-combat-relayout.png` | 已被 20:53 更正取代 |
| 20:53 右上角版 | `.tmp/pixel-combat-rightgroup.png` | 视角 + 双发射键移到右上角 |
| 20:57 紧凑版 | `.tmp/pixel-combat-compact.png` | 中间五个按钮缩小并居中 |
| **21:14 放大版（最终）** | `.tmp/pixel-combat-bigview-final.png` | 右上角三个控件放大 |

20:57 紧凑版触摸 → `/input`（校零 → 解锁 → 触摸 → 上锁）：

| 触摸 | `/input` 读到的量 | 判定 |
|---|---|---|
| 视角区右 100px / 上 80px | `vx=0.834`、`vy=0.668`；`r=0`、`buttons=0` | ✅ |
| 脚舵条左→右 | `r=0.480`；`vx/vy=0` | ✅ |
| **机炮**长按 900ms | `buttons=2048`，**只有 bit11** | ✅ 与投放完全分离 |
| **武器投放**长按 900ms | `buttons=64`，**只有 bit6** | ✅ 与机炮完全分离 |
| 武器 ↑ / ↓ | bit3 / bit4 | ✅ |
| 锁定 / 干扰弹 | bit5 / bit10 | ✅ |
| 松手 + 点上锁 | 五轴全 0、`buttons=0`，vJoy `alive/ok=true` | ✅ |

右上角版另测一轮（`vx=0.843/vy=0.674`、`r=0.470`、机炮 bit11、投放 bit6），
说明多次重排都没碰坏输入接线。除 168dp 试错版（右下角状态字被挤没，见 21:14 补充）
外，各版截图均无重叠、无文字截断。

`tests/test_export_lua.py` **42/42**；`tests/integration_test.py` 全量离线闭环回归
**85/85 通过、0 失败**（21:14 又加了 T-STAT-012）。**T-STAT-011** 现在同时守：`GUN_FIRE=11`、两个键都被调用、
源码顺序 绿点盘<视角<发射<脚舵、视角靠右（`Alignment.CenterEnd`）、
中间按钮为固定小尺寸、`BINDING.md` 有 BTN12 —— 左右位置或尺寸再被改回去都会挡住。
11/11 真机链路、功能层 VERIFY 5/5 未受本次手机端改动影响。

> 这次仍只验到「手机 → 桥接 → vJoy 输入」这一跳。`BTN7` 语义改了以后，
> **各机型在 DCS 里的绑定要按 `BINDING.md` §2 重绑一次**，否则打出去的还可能是机炮。

### 21:14 补充：右上角三个控件放大（最终交付版）

用户：「机炮，武器，视角太小了，尤其是视角」。

| 项 | 之前 | 现在 |
|---|---|---|
| 右列宽 | 150dp | **220dp** |
| 视角 `ViewPad` | 96dp 正方形，标签 10sp | **160dp 正方形，标签 13sp** |
| 机炮 / 武器键 | 约 72×60dp，13/10sp | 约 107×**84dp**，**18/12sp** |
| 视角映射半径 | 38dp | **70dp**（`min(宽,高)/2-10` 自动跟随尺寸） |
| 状态条 | 右下角两行 | 中间留白处**一行** |

**试错记录**：先做了 168dp 视角，真机截图 `.tmp/pixel-combat-bigview.png` 发现
右下角两行状态字被挤成 0 高 —— 右列 168+5+84 = 257dp 超过主体约 256dp。
改成 160dp，把状态合并成一行、挪到中间 `Box` 的 `Alignment.BottomCenter`，
右列底部只留 `Spacer(weight(1f))` 和脚舵隔开。最终截图
`.tmp/pixel-combat-bigview-final.png`：三个控件明显放大、状态字完整、无重叠无截断。

给共享控件加了可选参数（默认值不变，起降页与中间按钮不受影响）：
`ViewPad(labelSp)`、`GuardButton(textSp, subSp)`；映射半径随尺寸自动变，
拖满舵行程变长、控制更细，松手回中不变。

真机 `/input`（校零 → 解锁 → 触摸 → 上锁，20ms 轮询）：

| 触摸 | 读到的量 | 判定 |
|---|---|---|
| 视角区右 165px / 上 120px | `vx=0.825`、`vy=0.600`；`r=0`、`buttons=0` | ✅ |
| 脚舵条左→右 | `r=0.480`；`vx/vy=0` | ✅ |
| 机炮长按 900ms | `buttons=2048`，**仅 bit11** | ✅ |
| 武器投放长按 900ms | `buttons=64`，**仅 bit6** | ✅ |
| 武器 ↑/↓、锁定、干扰弹 | bit3/4、bit5、bit10 | ✅ |
| 松手 + 点上锁 | `vx/vy/r=0`、`buttons=0`；上锁后五轴全 0，vJoy `alive/ok=true` | ✅ |

> 松手瞬间读到 `x=0.182 / y=-1.0` 是手机姿态轴（测试过程中手机被摆动的残留），
> 不是视角 / 按钮串扰；上锁后归零，与本次改动无关。

新增 **T-STAT-012** 守「右列 220dp / 视角 160dp + 13sp / 发射键 84dp + 18sp」，
防止以后又缩回 96dp。全量离线回归 **85/85 通过、0 失败**，`test_export_lua.py` **42/42**。

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

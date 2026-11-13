# 座舱功能语义层 · 能力矩阵与测试计划

> 2026-11-13｜回答「雷达模式/返回/状态检测准确性、塔康输入、航路点、无线电频率、武器选择都测了吗」
> **结论：这些功能层此前一项都没测。** 之前 82 项离线回归 + 11 项真机回归测的是「链路层」：
> 命令发得出去、回执对得上、状态量回得来、页面状态机跟得上，**不验证具体座舱功能是否生效**。

---

## 1. 为什么不能笼统说「测了」

链路层通过 ≠ 功能生效。举例：按 `L1=RWS` 收到 `dbg=47:3277:D` 只证明
「设备方法被调用了」，不能证明雷达真的切到 RWS —— 因为 **DCS 根本不导出雷达模式**。
所以每一项必须先回答「有没有可信的状态量可判」，再决定怎么测、测到哪一层。

| 级别 | 含义 |
|---|---|
| `VERIFY` | 有明确状态量可判，能证明功能真的变了 |
| `INDIRECT` | 只能看页面文字 / 回执，不能证明功能生效 |
| `LIMIT` | DCS 接口硬限制，只能做能力探测，不判通过失败 |
| `SKIP` | 需要额外授权（写 `/input` 会动 vJoy） |

---

## 2. 能力矩阵（依据真机 `dcsprobe.json` 探针 + 源码）

| 你问的功能 | 能不能从状态量验证 | 可用判据 | 硬限制 |
|---|---|---|---|
| **雷达 · 开关状态** | ✅ `VERIFY` | `sys.radar` ← `SelfData.Flags.RadarActive`；可用 probe 直读比对 | — |
| **雷达 · 模式 RWS/TWS/…** | ❌ `LIMIT` | 只能看 `sys.mfd` 的模式菜单文字 | `LoGetRadarInfo` **函数不存在**；`LockedTargetInformation`/`TargetInformation`/`SightingSystemInfo` 全返回 nil |
| **雷达 · 返回能力** | ⚠️ `INDIRECT` + `VERIFY` | D3 回主菜单可判（`CHKLS` 回来）；RTN / U5 退出只能看页面 | 页面状态靠元素名反推，部分页无指纹 |
| **状态检测准确性** | ✅ 可全量测（离线） | `tests/mfd_recognition_test.py` 用 57 页自身指纹自识别 | 41 页 DCS 不导出元素名指纹 |
| **塔康输入** | ❌ 数值 `LIMIT`，跳转 `INDIRECT` | 按键回执 + 页面跳转 | `LoGetNavigationInfo = __nil__`；`UP_U3_TACAN` / `UP_U3_TACAN_Prog` 的 `e` 为 `None`（无元素名指纹）；`mfd_tokens` 只留元素名+全大写词，**动态数字被丢弃** |
| **航路点设置** | ⚠️ 窗口文本 `VERIFY`，数值 `LIMIT` | `sys.ufcp` 第一窗（`FP-A 01` 这类飞行计划/航点文本，**含数字**） | `LoGetNavigationInfo = nil`，没有航路点状态量 |
| **无线电频率设置** | ⚠️ 波道号 `VERIFY`，频率 `LIMIT` | `sys.ufcp` 第四窗（`001 001` = COM1/COM2 波道） | 手册：频率由数据卡预存，UFCP 显示的是**波道号不是 MHz**；DCS 不导出频率 |
| **武器选择** | ✅ `VERIFY` | `sys.st` / `wn` / `wc` / `wl` ← `PayloadInfo.CurrentStation` + `Stations` | 刚进任务 `CurrentStation=0`（没选），要按过武器切换键才有值 |

**一句话**：雷达模式、塔康频道数值、无线电真实频率、航路点数值这四类
**在当前 DCS 导出能力下无法做输入→状态闭环验证**，只能验证「按键发出、页面跳转、UFCP 窗口文本变化」。
要拿到真值只有上 DCS-BIOS（读座舱参数），属于 P2 工程。

---

## 3. 已经做完的（不需要 DCS 在跑）

### 3.1 状态检测准确性 · 全量自识别测试

`python tests/mfd_recognition_test.py`（完整复刻 `panel.html` 的 `GENERIC_PRE` / `scoreSeg` / `applyScreenText` 兜底）：

```
页面数 57｜有元素名指纹的页 20
✅ 正确识别自身      : 12/57
❌ 认成别的页        :  4
❓ 认不出 / 无指纹   : 41
🚫 下半区串到上半区  :  0   ← BUG-06 修复有效
```

| 认错的页 | 被认成 | 原因 |
|---|---|---|
| `UP_U1_RDR_AA_CNTL` | `UP_U1_RDR_AA` | CNTL 是雷达页浮层，共用底层元素，主页命中数更高 |
| `UP_U1_RDR_AG_CNTL` | `UP_U1_RDR_AG` | 同上 |
| `UP_R1_SMS_AG` | `UP_R1_SMS_AA` | AA/AG 共用 `SMS_Base` 元素 |
| `UP_R3_BIT` | `UP_MainMenu` | BIT 页只有 `osb_txt_`，被主菜单兜底捞走 |

分功能区准确率：雷达 3/5、下半区 3/7、其他 5/18、外挂 1/16、**DATA 0/11**。
`UP_U3_TACAN`、`UP_U3_TACAN_Prog`、`UP_L4_DATA` 及 DATA 全系、SMS 子页、INS/APR/POD
都**没有元素名指纹**，设计上只能靠按键推演 + 下拉框手选 —— 这就是「状态检测准确性」的真实上限。

> 这 4 个误判是**已知的指纹重叠**（源码里已用 `n` 跳转表兜底），不是上一轮修复引入的回归；
> 但确实是准确性的短板。要不要改打分规则需要真机逐页确认，暂未改动算法。

### 3.2 真机结构 / 接口普查

用 DCS 自带 `dev=0,cmd=7` probe 通道只读取得（probe.lua 用完已恢复）：
`NavigationInfo=__nil__`、`RadarInfo=__missing__`、`PayloadInfo.Stations` 有内容、
`SelfData.Flags.RadarActive=false`。UFCP 四窗 `FP-A 01|CAS MAN||001 001`。

---

## 4. 真机测试已执行（18:48 用户重启任务 + USB 后）

脚本：`tests/live_features_test.py --allow-input`。
**结果：`VERIFY 5/5 通过`，另有 5 项 `INDIRECT`、3 项 `LIMIT`、1 项 `SKIP`。**
完整逐项证据见 `docs/TEST-REPORT-FEATURES.md`。

| ID | 项 | 级别 | 结论 |
|---|---|---|---|
| F-RADAR-01 | 雷达开关读数准确性 | VERIFY | ✅ probe `false` = `sys.radar False` |
| F-RADAR-02 | 雷达模式接口能力 | LIMIT | ❌ `LoGetRadarInfo` 不存在 |
| F-RADAR-03 | 中屏 U1 弹模式菜单 | INDIRECT | ✅ 10 个模式 token 全中、`bp` +1 |
| F-RADAR-04 | L1=RWS 后返回雷达页 | INDIRECT | ✅ 菜单消失；无法证明雷达真换模式 |
| F-RADAR-05 | D3 随时回主菜单 | VERIFY | ✅ `CHKLS` 回来 |
| F-TACAN-01 | 主菜单 U3 进塔康主页 | INDIRECT | ✅ 回执 `:D`、`acn` 递增；页面无指纹 |
| F-TACAN-02 | U1 进程序页 → L1 选 TCN01 | INDIRECT | ✅ 两条 `:D` 回执；数值读不到 |
| F-TACAN-03 | 塔康频道数值可读性 | LIMIT | ⚠️ 原始 dump 有数字，`sys.mfd` 丢了 |
| F-NAV-01 | UFCP DST/4 → 航路点窗口 | VERIFY | ✅ 四窗变 `DST 00｜431718 N｜0402112E｜+ 06556` |
| F-NAV-02 | UFCP RTN 退出功能 | VERIFY | ✅ 回 `FP-A 01｜CAS MAN｜｜001 001` |
| F-RADIO-01 | 电台波道步进是否生效 | INDIRECT | ⚠️ 按键进编辑态，波道号**未变** |
| F-RADIO-02 | 频率数值可读性 | LIMIT | ❌ 第四窗是波道号，不是 MHz |
| F-WPN-01 | 武器切换 → `sys.st` | SKIP | ⏸ 本任务 7 挂点全 `x0`，无挂载 |
| F-WPN-02 | 挂载清单可读性 | VERIFY | ✅ 无挂载时 `wl=null` 是正确行为 |

### 两处「失败」的定性（都不是产品缺陷）

1. **电台波道步进**：首轮直接按 `PNT_730` 无反应 —— 手册 1.10-c 要求
   「先让光标固定在参数最左一位、3 秒内拨动开关」。查 `clickable_defs.lua` 确认
   `PNT_730` = `default_2_way_spring_switch`（`arg_value={1,-1}`，释放回 0），我们的 `1→0` 序列正确。
   紧凑序列实测：`L4` 后原始 `list_indication(6)` dump 出现 `txt_win4_fill`（进编辑态），
   但 RTN 回常态第四窗仍是 `001 001`。**按键到达、功能未确认**，已如实降级为 `INDIRECT`。
   正确前置序列（可能需电台面板 TR/超控/P/PRE/ENT 流程）尚未找到，列为待排查。
2. **武器选择**：本任务 `Stations` 7 项全 `x0`（无挂载），`CurrentStation` 恒 0，
   `sys.st/wn/wc=null` 是正确行为；`/input` 链路单独验证通（seq 525→527、vJoy alive/ok）。
   已改为 `SKIP` 并注明「需带挂载的任务」，不再误报失败。

### 复现

```bash
python tests/live_features_test.py                  # 不含武器切换
python tests/live_features_test.py --allow-input    # 额外测武器切换（有挂载时才有意义）
```

前提：DCS 在座舱里（`has_data=true`）。脚本会备份/恢复用户原有的 `probe.lua`、
自动清理诊断文件；结束用中屏 D3 回主菜单、UFCP RTN 回常态。
本次收尾实测：`60.1Hz / bad=0 / age=10ms`、中屏主菜单、无命令文件残留。

---

## 5. 如果要把「测不了」变成「测得起来」

按代价从小到大：

1. **塔康 / MFD 页动态数字**：`Export.lua::mfd_tokens` 现在只收 `[a-z][a-z0-9_]*` 和全大写词，
   把短数字串（`TCN01`、`001 001`、频道号）也收进 token，`sys.mfd` 就能带上数值 → 改 `Export.lua`，**要重启任务**。
2. **航路点 / 频率**：把 UFCP 四窗文本按语义拆成独立字段（`sys.wpt` / `sys.com1` / `sys.com2`），
   面板直接显示，测试也能直接断言 → 改 `Export.lua` + `panel.html`。
3. **雷达模式 / 锁定 / 航路点数值**：DCS 导出 API 没有。
   ⚠️ **但上 DCS-BIOS 也解决不了** —— 查证 JF-17 的 BIOS 模块（约 444 项）里
   `RADAR/RWS/TWS/TACAN/TCN/WPT/SMS/STATION/MFCD 页面文本` 精确命中全为 0，
   只有 `UFCP_LINE_1~4`（我们已经有）和 `RADIO_LINE_1/2`。详见 `docs/BIOS-ASSESSMENT.md`。
4. **电台波道操作序列**：需按手册 1.10 / 电台面板流程（TR → 超控 → P → PRE → 数字 → ENT）
   逐键试出正确序列，再决定 `panel.html` 的 `+`/`−` 键要不要加「先选中参数」的提示。

这些都不在「链路层测试」范围内，需要你决定是否投入。最小且收益最大的是第 1 条：
改 `mfd_tokens` 收数字，0.5–1 人日，不需要引入 DCS-BIOS。

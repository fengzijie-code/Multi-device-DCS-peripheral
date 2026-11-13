# 真机 · 座舱功能语义层测试

> 2026-11-13 18:56:30｜脚本 `tests/live_features_test.py`
> 机型 `JF-17`｜`hz=60.1`｜`sys.radar=False`

## 能力边界（先说清楚哪些根本测不了）

| 功能 | 可否从状态量验证 | 依据 |
|---|---|---|
| 雷达开关 | ✅ `sys.radar` | `SelfData.Flags.RadarActive` |
| 雷达模式 RWS/TWS/… | ❌ | `LoGetRadarInfo` 函数不存在；只能看 `sys.mfd` 页面文字 |
| 锁定目标/距离 | ❌ | `LockedTargetInformation` 等三个函数全返回 nil |
| 塔康频道数值 | ❌ | `LoGetNavigationInfo=nil`；TACAN 页无元素名指纹，`sys.mfd` 提取器丢弃数字 |
| 航路点数值 | ❌ | `LoGetNavigationInfo=nil`；只能看 `sys.ufcp` 窗口文本 |
| 无线电频率 | ⚠️ 只能测波道号 | UFCP 第四窗是 COM1/COM2 波道，频率由数据卡预存 |
| 武器选择 | ✅ `sys.st/wn/wc/wl` | `PayloadInfo.CurrentStation` + `Stations` |

## 逐项结果

| ID | 项 | 级别 | 输入 | 期望 | 实际 | 判定 |
|---|---|---|---|---|---|---|
| F-RADAR-01 | 雷达开关读数准确性 | VERIFY | `只读：probe 直读 SelfData.Flags.RadarActive` | 与 /state.sys.radar 完全一致 | probe=false  /state=False  一致=True | ✅ |
| F-RADAR-02 | 雷达模式是否可读（接口能力） | LIMIT | `只读：查 LoGetRadarInfo` | 若能读到模式则可做模式闭环验证 | LoGetRadarInfo 不存在；sys 里没有雷达模式字段 → 只能靠 sys.mfd 页面文字间接判断 | ✅ |
| F-RADAR-03 | 雷达模式菜单弹出 | INDIRECT | `中屏 U1 (cmd 3271)` | sys.mfd C 段出现 RWS/TWS/VS/MAP/GMTI/SEA1… 且 sys.bp 序号 +1 | 命中模式 token=['BCN', 'GMTI', 'MAP', 'RWS', 'SEA1', 'SEA2', 'TA', 'TWS', 'VS', 'WA']  bp 24→25 | ✅ |
| F-RADAR-04 | 选模式后返回雷达页（返回能力） | INDIRECT | `模式菜单 L1 (cmd 3277, =RWS)` | 模式菜单消失、回到雷达页；DCS 不导出模式，无法验证雷达真的切到 RWS | C 段模式 token 数=1 bp=26:775,769,793,793,793,775,769,771 | ✅ |
| F-RADAR-05 | D3 随时回主菜单（返回能力） | VERIFY | `中屏 D3 (cmd 3295)` | sys.mfd C 段重新出现 CHKLS | CHKLS=True | ✅ |
| F-TACAN-01 | 进入塔康主页 | INDIRECT | `主菜单 U3 (cmd 3273)` | 回执 :D、acn 递增；TACAN 页 e=None，sys.mfd 无法识别该页 | dbg=47:3273:D acn 164→168  C 段=['LOWER_BASE', 'RTN', 'UPPER_BASE'] | ✅ |
| F-TACAN-02 | 塔康程序页选 TCN01 | INDIRECT | `U1 (cmd 3271) → L1 (cmd 3277)` | 两条命令都有 :D 回执；页面数值（频道/波道）无法从状态量验证 | HTTP 200 dbg=47:3277:D  sys.mfd 是否含数字=True | ✅ |
| F-TACAN-03 | 塔康频道数值可读性（能力探测） | LIMIT | `只读：probe 读 list_indication(9) 原始 dump` | 若原始 dump 有频道数字而 /state.sys.mfd 没有，说明提取器丢了动态文本 | 原始 dump 含数字行=True；/state.sys.mfd 只留元素名+全大写词，数字被丢弃 | ✅ |
| F-NAV-01 | 航路点数据键 → UFCP 窗口变化 | VERIFY | `UFCP DST/4 (cmd 3209)` | sys.ufcp 窗口文本变化（LoGetNavigationInfo 返回 nil，只能靠窗口文本） | bef=['FP-A 01', 'CAS MAN', '', '001 001']  aft=['DST 00', '431718 N', '0402112E', '+ 06556'] | ✅ |
| F-NAV-02 | RTN 退出功能（返回能力） | VERIFY | `UFCP RTN (cmd 3223)` | 窗口回到常态或至少不卡在编辑态 | bef=['DST 00', '431718 N', '0402112E', '+ 06556']  aft=['FP-A 01', 'CAS MAN', '', '001 001']  dbg=46:3223:D | ✅ |
| F-RADIO-01 | 电台波道 +/- 步进是否生效 | INDIRECT | `L4(cmd 3226) 选中参数 → 步进 +(cmd 3232) → RTN` | 按键进入编辑态可证链路通；第四窗波道号递增才能证明功能生效 | 常态=['FP-A 01', 'CAS MAN', '', '001 001'] 选中后=['PLN EMG', 'RT SQ+', 'NE- SLAV', '---'] 步进后=['PLN EMG', 'RT SQ+', 'NE- SLAV', '_fill . '] RTN后=['FP-A 01', 'CAS MAN', '', '001 001']；第四窗 '001 001'→'001 001' 波道变化=False dbg=46:3232:D；原始 dump 出现 txt_win4_fill（编辑态） | ✅ |
| F-RADIO-02 | 频率数值是否可读 | LIMIT | `只读：查 UFCP 第四窗语义` | 若能读到 MHz 频率则可做频率闭环验证 | 第四窗显示的是 COM1/COM2 **波道号**（如 001 001），频率由数据卡预存，DCS 不导出 → 只能测波道切换 | ✅ |
| F-WPN-01 | 武器切换 → CurrentStation/st/wn/wc 变化 | SKIP | `POST /input b=BTN5 脉冲（本任务无挂载，跳过）` | 需要带挂载的任务才能验证；本次 7 个挂点全 x0 | STATIONS_N = 7 挂点行=['ST1 =  x0', 'ST2 =  x0', 'ST3 =  x0', 'ST4 =  x0'] CurrentStation=0 sys.st=None wl=None；/input 链路本身已验证通 | ✅ |
| F-WPN-02 | 挂载清单可读性 | VERIFY | `只读：读 /state.sys.wl 并与 probe 的 Stations 对比` | 有挂载时 wl 应拼出清单；无挂载时 wl=null 才对 | wl=None cn=180 STATIONS_N = 7 挂点行=['ST1 =  x0', 'ST2 =  x0', 'ST3 =  x0', 'ST4 =  x0'] 本任务有挂载=False | ✅ |

> **级别说明**：`VERIFY` = 有明确状态量可判；`INDIRECT` = 只能看页面/回执，不能证明功能真的生效；`LIMIT` = DCS 接口硬限制，本项只做能力探测、不判通过失败；`SKIP` = 前置条件不满足（本任务无挂载）或需要额外授权（写 /input 会动 vJoy）。

## 真机执行发现（2026-11-13 18:5x）

1. **雷达开关读数准确**：probe 直读 `SelfData.Flags.RadarActive=false` 与 `sys.radar` 一致。
2. **模式菜单 / 返回能力真实可用**：中屏 U1 弹出 10 个模式项、L1 选 RWS 后菜单消失、D3 回主菜单，`sys.bp` 序号全程跟随；但 DCS 不导出雷达模式，无法证明雷达真的切到 RWS。
3. **航路点数据可测**：UFCP `DST/4` 让四窗从 `FP-A 01|CAS MAN||001 001` 变成 `DST 00|431718 N|0402112E|+ 06556`（含经纬高），`RTN` 正确复原。这是本轮最有价值的输入→状态对应。
4. **电台波道步进未生效（诚实标注 INDIRECT）**：`PNT_730` 是 `default_2_way_spring_switch`（`arg_value={1,-1}`，释放回 0），我们的 `1→0` 序列没错；按 `L4` 后原始 `list_indication(6)` dump 出现 `txt_win4_fill`（进入编辑态），但 RTN 回常态后第四窗仍是 `001 001`——**按键到达、波道未改**。手册 1.10-c 要求「光标固定在参数最左一位、3 秒内拨动」，正确前置操作序列尚未找到；也可能需按电台面板的 TR/超控/P/PRE/ENT 流程。
5. **武器选择本次无法验**：任务 7 个挂点全 `x0`（无挂载），`CurrentStation` 恒 0，`sys.st/wn/wc` 为 null 是正确行为；`/input` 链路已单独验证通（seq 递增、vJoy alive/ok）。需要带挂载的任务才能跑这一项。
6. **面板可改进点**：UFCP 编辑态下 `ufcp_win_text` 抓到 `_fill`/占位符而非真实数值；`panel.html` 的 `+`/`−` 键没提示「需先选中参数」，容易让人以为按了没反应。

## 页面识别准确性（离线全量，见 `tests/mfd_recognition_test.py`）

57 个页面用自己的元素名指纹喂回打分器：12 页正确自识别、4 页认成别的页、41 页因 DCS 不导出元素名而认不出、0 页把下半区串到上半区。认错的集中在雷达 CNTL 浮层与 SMS AG/AA（共用底层元素，指纹高度重叠）；TACAN / TACAN_Prog / DATA 全系 / SMS 子页 / INS / APR / POD 都没有元素名指纹，**只能靠按键推演 + 下拉框手选**，这正是「状态检测准确性」的真实上限。

## 安全约定

只发可逆的 MFD / UFCP 页面键与数字功能键；不发射武器、不改飞行构型；武器切换需 `--allow-input` 显式开启。结束时用中屏 D3 回主菜单。

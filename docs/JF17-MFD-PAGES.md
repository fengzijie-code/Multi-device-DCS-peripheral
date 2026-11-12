# JF-17 MFD 各页面的键位标签（从 DCS 代码直接导出）

> **这文件不是手抄的**。数据源：`D:\DCS World\Mods\aircraft\JF-17\Cockpit\Scripts\MFCD\Indicator\*.lua`
> —— 这就是 MFD 画面的绘制代码，每个周边键的标签都是一条 `{value="XXX", cx=…, cy=…}`，
> 坐标常量直接对应物理键（`MFCD_FONT_UD1_X…UD5_X` = 上排 U1–U5，
> `MFCD_FONT_L_HORI_X/R_HORI_X` + `MFCD_FONT_LR1_Y…LR8_Y` = 左右列，`MFCD_FONT_D_Y` = 下排）。
>
> 重新生成：`python tools/dump-mfd-pages.py`

**两个必须知道的局限**：

1. **只有静态标签**。动态读数（距离刻度、PRF、扫描行数、目标信息）在代码里是 `ctrls={{...}}` 加运行时参数，
   没有 `value` 字符串，所以这张表里看不到 —— 但它们照样占着某个键的位置，实测时按一下就知道。
2. **标签 ≠ 当前功能**。同一条标签可能只在某些子模式下显示（例如 `EXP` 只在扩展显示时出现）。
   表里给的是「这个键上可能写什么」，最终仍以屏幕为准。

---

## 一、主菜单（任意屏按 D3 进入）

这是最该背下来的一页 —— 所有画面都从这里进。

```
        U1    U2     U3      U4     U5
       RDR   INS   TACAN    APR    POD
  ┌──┬───────────────────────────────┬──┐
L1│  │                               │  │R1  SMS
L2│  │            MENU               │  │R2  CMBT
L3│  │                               │  │R3  BIT
L4│  │                               │  │R4  CHKLS
  │  │                               │  │R5  PFL
  └──┴───────────────────────────────┴──┘
L1 HSD   L2 EFIS   L3 CLNK   L4 DATA
```

| 键 | 内容 | 键 | 内容 |
|---|---|---|---|
| U1 | RDR 雷达 | L1 | HSD 水平状态 |
| U2 | INS 惯导 | L2 | EFIS 电子飞行仪表 |
| U3 | TACAN 塔康 | L3 | CLNK 数据链 |
| U4 | APR 应答/识别 | L4 | DATA 数据（内含 RLS/NAV/AS/FUEL…） |
| U5 | POD 吊舱 | R1 | SMS 外挂管理 |
| R2 | CMBT 战斗 | R3 | BIT 自检 |
| R4 | CHKLS 检查单 | R5 | PFL 可编程功能列表 |

> 手册 p53 说的「主菜单上按 L4 进 DATA」在这里得到印证。
> `UP_L4_DATA` 页再往下：L1 RLS / L2 NAV / L3 AS / L4 FUEL，R1 DST / R2 FCS / R3 ENG / R4 DTC。

---

## 二、雷达页（中显按 D2 进入，或主菜单 U1）

```
        U1    U2     U3     U4     U5
      (模式)  —     STBY   SIL   CNTL
  ┌──┬───────────────────────────────┬──┐
L1│  │                               │  │R1
L2│  │          雷达画面              │  │R2
L3│  │                               │  │R3
L4│  │                               │  │R4
L5│  │                               │  │R5 (PRF)
  └──┴───────────────────────────────┴──┘
L1 BIND   L2 EXP   L3 60   L4 NOR   L5 4BR
```

**左列是搜索参数**，这一页最有用的就是它们：

| 键 | 标签 | 含义 | 按了会怎样（手册） |
|---|---|---|---|
| L1 | `BIND` | RWS/TWS 绑定状态 | `rdr_aa_bind_state` |
| L2 | `EXP` | 扩展显示 | 放大中央区域 |
| **L3** | `60` | **方位角宽度** | 循环 ±60 / ±30 / ±15 |
| **L4** | `NOR` | **天线高度稳定** | 循环 NORM / …（图注 N「天线高度稳定模式」） |
| **L5** | `4BR` | **扫描行数** | 循环 4 行 / 2 行 / 1 行 |
| U3 | `STBY` | 待机 | 进/出 STBY |
| U4 | `SIL` | 静默 | 进/出 SIL |
| **U5** | `CNTL` | **雷达控制菜单** | 进 CNTL（手册 4.4.7），标签在 `UP_U1_RDR_Base` |
| R5 | （读数） | PRF 设置 | 图注 G「雷达重复频率选择」，代码里是 `rdr_aa_prf_setting` |

> **注意 U2 是空的**：源码里 `--[[ EXP ... ]]` 被注释掉了（`UP_U1_RDR_AA.lua` 第 106 行附近），
> 所以上排第二个键现在没有标签。同理 L1 是 `BIND` 而不是 `DGFT` —— `DGFT` 那段也是注释掉的旧代码。
> **这正是必须过滤 Lua 注释的原因**：第一版解析器把注释里的 `DGFT` 当成现状，读错了一个键。
>
> 手册那张 RWS 截图里 U3 写的是 `IFF`，代码里现在是 `STBY` —— 截图来自旧版本，
> **以代码为准**（`rdr_state_draw` 一个控制器同时管 STBY / SIL 的显示）。

> **这张表直接回答了之前那个「雷达模式怎么切」的问题**：
> U1 的标签是动态画出来的（代码里没有静态 value），手册图注 A 明确写
> 「雷达工作模式（按压此键会出现模式菜单）」→ **按 U1 弹模式菜单**。
> 菜单页 `UP_U1_RDR_Mode` 的键位是 **L1–L5 = 条目 1–5，R1–R5 = 条目 6–10**。
> 手册第四节的空对空模式正好五个（RWS / TWS / VS / SAM / DTT），
> 空对地雷达模式也是五个（MAP / FTT / DBS / GMTI / GMTT）——
> 所以**条目 1–5 是 AA、6–10 是 AG** 是最合理的推断，明天一按就验证了。

---

## 三、全部页面（自动导出，60 个）

按 `上排 / 左列 / 右列 / 下排` 排好序；标签里的 `/` 表示屏幕上是**竖排**文字（如 `C/A/G/E` 实际是 C、A、G、E 竖着写）。

| 页面脚本 | 键 = 屏幕标签 |
|---|---|
| `DOWN_AFINFO` | **R6** NEXT · **R7** BACK · **R8** RTN |
| `DOWN_CLINK` | **R8** RTN |
| `DOWN_EPI1` | **L6** NORM · **R6** EPI1 · **R8** RTN |
| `DOWN_EPI2` | **L6** NORM · **R6** EPI2 · **R8** RTN |
| `DOWN_MainMenu` | **L6** AFD · **L7** SMS · **R6** EPI1 · **R7** EPI2 · **R8** RTN |
| `DOWN_SMS` | **R8** RTN |
| `FULL_BASE` | **D2** D2 · **D3** SOI · **D4** D4 |
| `UP_DATA_AS` | **U1** AS DATA |
| `UP_DATA_DEdit` | **L1** 1 · **L2** 2 · **L3** 3 · **L4** 4 · **L5** 5 · **R1** 6 · **R2** 7 · **R3** 8 · **R4** 9 · **R5** 0 |
| `UP_DATA_DST` | **U1** DST · **U2** FP-A · **U4** CPY · **U5** CLR · **L2** STEP · **L3** BACK |
| `UP_DATA_DTC` | **U1** DATA · **U5** ALL · **L1** NAV · **L2** SMS · **L3** CNI · **L4** APR · **L5** OAP · **R1** EWS · **R5** ENT |
| `UP_DATA_ENG` | **U1** ENG |
| `UP_DATA_FCS` | **U1** FCS · **U5** SPCHK |
| `UP_DATA_FUEL` | **U1** FUEL |
| `UP_DATA_NAV` | **U1** NAV DATA |
| `UP_DATA_RLS` | **U1** RLS · **U5** RTN · **L1** RLS1 · **L2** RLS2 · **L3** RLS3 · **L4** RLS4 · **L5** RLS5 · **R1** RLS6 · **R2** RLS7 · **R3** RLS8 · **R4** RLS9 · **R5** RLS10 |
| `UP_DATA_SPCHK` | **U1** SPCHK · **U5** FCS |
| `UP_EDIT` | **L1** 1 · **L2** 2 · **L3** 3 · **L4** 4 · **L5** 5 · **R1** 6 · **R2** 7 · **R3** 8 · **R4** 9 · **R5** 0 · **D1** CLR |
| `UP_L1_HSD` | **U5** TRU |
| `UP_L2_EFIS` | **L5** NORM · **R5** ILS |
| `UP_L3_CLINK` | **U1** CLINK |
| `UP_L3_CLINK_List` | **U1** RTN |
| `UP_L4_DATA` | **U1** DATA · **L1** RLS · **L2** NAV · **L3** AS · **L4** FUEL · **R1** DST · **R2** FCS · **R3** ENG · **R4** DTC |
| `UP_MainMenu` | **U1** RDR · **U2** INS · **U3** TACAN · **U4** APR · **U5** POD · **L1** HSD · **L2** EFIS · **L3** CLNK · **L4** DATA · **R1** SMS · **R2** CMBT · **R3** BIT · **R4** CHKLS · **R5** PFL |
| `UP_POD_MIL` | **U1** DLPOD · **U2** NAR · **U3** AUTO · **U4** MODE · **L3** CRUS · **R1** M1 · **R2** M2 |
| `UP_POD_TVIR` | **L5** RE/FOCUS · **R1** BHOT · **R5** 5 M |
| `UP_POD_WMD7` | **U1** WMD7 · **U2** MODE · **U4** WHOT · **L1** C/A/G/E · **R1** NAR · **R2** L/S/S · **R3** C/O/D/E · **R4** L/S/R · **R5** RE/FOCUS |
| `UP_R1_SMS_AA` | **U3** NORM · **R2** MSL STATE · **D1** CLR · **D2** CMBT · **D4** JET |
| `UP_R1_SMS_AA_Base` | **U1** A/A1 · **U2** FEED · **U5** LOAD · **L2** GUN |
| `UP_R1_SMS_AA_Gunsight` | **L3** LCOS · **L4** SSLC · **L5** SS |
| `UP_R1_SMS_AA_Limiter` | **L3** OFF · **L4** 0.2 · **L5** 0.5 |
| `UP_R1_SMS_AA_Wpn` | **L3** AA 1 · **L4** AA 2 · **L5** AA 3 · **R3** AA 4 · **R4** AA 5 · **R5** AA 6 |
| `UP_R1_SMS_AG` | **L1** CNTL · **R2** MSL STATE · **D1** CLR · **D2** CMBT · **D4** JET |
| `UP_R1_SMS_AG_Base` | **U1** A/S1 · **U2** FEED · **U5** LOAD · **L2** GUN |
| `UP_R1_SMS_AG_Fuze` | **L3** SAFE · **L4** NOSE · **L5** TAIL · **R3** N+T |
| `UP_R1_SMS_AG_Intv` | **L3** 0 · **L4** 0.1 · **L5** 0.2 · **R2** 0.4 · **R3** 0.8 · **R4** 1.2 · **R5** 1.6 |
| `UP_R1_SMS_AG_Mode` | **L3** AUTO · **L4** CCIP · **L5** DTOS · **R1** VIP · **R2** DIR |
| `UP_R1_SMS_AG_Profile` | **L1** CNTL · **D1** CLR |
| `UP_R1_SMS_AG_Qty` | **L3** 1/OFF · **L4** 2/0.2 · **L5** 4/0.5 · **R5** 6/0.5 |
| `UP_R1_SMS_AG_Wpn` | **L3** AG 1 · **L4** AG 2 · **L5** AG 3 · **R3** AG 4 · **R4** AG 5 · **R5** AG 6 |
| `UP_R1_SMS_Jet` | **U1** 2 · **U2** 3 · **U3** 4 · **U4** 5 · **U5** 6 |
| `UP_R1_SMS_Load` | **U1** 2 · **U2** 3 · **U3** 4 · **U4** 5 · **U5** 6 · **D1** CLR · **D2** COPY · **D4** SMS |
| `UP_R1_SMS_Load_Type` | **L2** BOMB · **L3** CLST · **L4** ROCK · **R2** MILS · **R3** FUEL · **R4** POD |
| `UP_R1_SMS_Load_Wpn` | **L1** PL-5E · **L2** SD-10 · **L3** C-802K · **L4** CM-802AKG · **L5** RKT-1 · **R1** MK-82 · **R2** MK-83 · **R3** WMD7 · **R4** STEP · **R5** BACK |
| `UP_R1_SMS_Prog` | **L2** AA 1 · **L3** AA 2 · **L4** AG 1 · **L5** AG 2 · **R2** AG 3 · **R3** AG 4 · **R4** AG 5 · **R5** AG 6 |
| `UP_R2_CMBT` | **U1** CMBT · **U2** FEED · **U5** LOAD · **L2** GUN · **L3** AUTO · **L4** CH · **L5** PRG02 · **R3** STBY · **R4** TYPE1 · **R5** F+B |
| `UP_R3_BIT` | **U1** LMFCD · **U2** RMFCD · **U3** CMFCD · **U4** HUD · **U5** EMMC · **L1** WMMC1M · **L2** WMMC2 · **L3** CNI · **L5** 1 · **R1** RDR · **R2** INS · **R3** SMS · **R4** RWR · **R5** OESP |
| `UP_R4_CHKLS` | **U1** CHLST · **U3** COLD |
| `UP_R5_PFL` | **U1** PFL · **U5** 1/1 · **L1** FCS · **L2** FIRE · **L3** ENG · **L4** INS · **L5** SMS · **R4** STEP · **R5** BACK |
| `UP_U1_RDR_AA` | **U3** STBY · **U4** SIL · **L1** B/I/N/D · **L2** E/X/P · **L3** 60 · **L4** N/O/R · **L5** 4/B/R |
| `UP_U1_RDR_AA_CNTL` | **U5** CNTL |
| `UP_U1_RDR_AG` | **U3** STBY · **U4** SIL · **L3** 60 |
| `UP_U1_RDR_AG_CNTL` | **U5** CNTL · **R4** BCN/00 |
| `UP_U1_RDR_Base` | **U5** CNTL |
| `UP_U1_RDR_Mode` | **L1** 1 · **L2** 2 · **L3** 3 · **L4** 4 · **L5** 5 · **R1** 6 · **R2** 7 · **R3** 8 · **R4** 9 · **R5** 10 |
| `UP_U2_INS` | **U1** INS |
| `UP_U3_TACAN` | **U1** TACAN |
| `UP_U3_TACAN_Prog` | **U1** TACAN · **L1** TCN01 · **L2** TCN02 · **L3** TCN03 · **L4** TCN04 · **L5** TCN05 · **R1** TCN06 · **R2** TCN07 · **R3** TCN08 · **R4** TCN09 · **R5** TCN10 |
| `UP_U4_APR` | **U1** APR · **U4**  · **U5**  |
| `UP_U5_POD` | **U1** POD · **L1** T/V/I/R · **R1** W/M/D/7 · **R4** M/I/L |

---

## 四、几处值得注意的

- **`DOWN_*` 是下半区**（R8 进小画面菜单）：`DOWN_MainMenu` 有 L6 AFD / L7 SMS / R6 EPI1 / R7 EPI2 / R8 RTN。
  也就是说**下半区和上半区是两套独立的键**，L6/L7、R6/R7 只在下半区有定义。
- **`UP_EDIT` 是数字键盘**：L1–L5 = 1–5，R1–R5 = 6–0，D1 = CLR。DATA 里输数字就靠它。
- **`SMS` 系列分得极细**：`_Wpn` 选武器、`_Mode` 选投放模式、`_Fuze` 引信、`_Qty` 数量、`_Intv` 间隔，
  每个子页只有 2–5 个键有定义，其余是空的 —— 空键按了没反应属于正常。
- **`BIT` 页**能逐设备自检（U1 LMFCD / U2 RMFCD / U3 CMFCD / U4 HUD / U5 EMMC，R1 RDR / R2 INS / R3 SMS / R4 RWR / R5 OESP），
  排查「这个设备活着吗」很有用。

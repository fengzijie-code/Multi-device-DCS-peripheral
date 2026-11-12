# JF-17 可操作控件清单

> 来源：`Mods/aircraft/JF-17/Cockpit/Scripts/clickabledata.lua` 解析结果
> 只收录**带中文注释**的控件 —— 没有注释的那些看不懂是什么，盲操作没意义。
>
> **命令号 = 元素ID + 2502**。这个偏移来自 `command_defs.lua`：
> `start_command = 3001`，然后 `for i=500,999 do click_cmds['PNT_'..i] = dcounter() end`，
> 而 `dcounter()` 是先加后返回。所以 `PNT_505` → `3007`。
>
> 用法：`POST /cmd  {"dev": 设备号, "cmd": 命令号, "val": 值}`
> 两档开关 val 用 0/1，三档用 0/0.5/1，按钮类先 1 再 0。


## FCS（设备号 35）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `513` | `3015` | default_2_position_tumb | TEF up/down 襟翼开关 |
| `527` | `3029` | default_2_position_tumb | 记录开关 |
| `528` | `3030` | default_2_position_tumb | EFCS强制开/自动 模拟备份开关 |
| `529` | `3031` | default_2_position_tumb | 航向/滚转增稳开关 |
| `530` | `3032` | default_2_position_tumb | 直连模式开关 |
| `531` | `3033` | default_2_position_tumb | BIT按钮 |
| `532` | `3034` | default_2_way_spring_switch | YAW配平 |
| `535` | `3037` | default_2_position_tumb | AG1/AG2切换开关 |
| `536` | `3038` | default_2_position_tumb | AA/AG切换开关 |
| `544` | `3046` | default_button | FCS重启按钮 |
| `733` | `3235` | default_2_way_spring_switch | 减速伞开关 |
| `733` | `3235` | default_3_position_tumb | 减速伞开关 |

## LIGHTS（设备号 4）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `512` | `3014` | default_3_position_tumb | 3档开关 LAND/OFF/TAXI 着陆/滑行灯开关 |
| `944` | `3446` | default_axis_limited | INST仪表照明旋钮 |
| `945` | `3447` | default_axis_limited | CONSOLE操纵台照明旋钮 |
| `946` | `3448` | default_axis_limited | FLOOD泛光灯旋钮 |
| `947` | `3449` | default_3_position_tumb | 3档开关 master 机外主照明开关 |
| `948` | `3450` | multiposition_switch_limited | 5档旋钮 编队灯旋转开关 |
| `949` | `3451` | multiposition_switch_limited | 5档旋钮 防撞灯旋转开关 |
| `950` | `3452` | default_3_position_tumb | 3档开关 航行灯亮/暗开关 |
| `952` | `3454` | default_3_position_tumb | 3档开关 防撞灯/牵引照明开关 |
| `963` | `3465` | default_2_position_tumb | 2档开关 AAR灯 |
| `964` | `3466` | default_axis_limited | AAR灯旋钮 |

## ENGINE（设备号 34）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `519` | `3021` | default_2_position_tumb | ENG contrl ON/OFF 发动机系统开关 |
| `520` | `3022` | default_2_position_tumb | 发动机空中启动开关 |
| `522` | `3024` | default_3_position_tumb | 发动机工作状态转换开关 作战/作战+训练/训练 三档开关 |
| `523` | `3025` | default_2_position_tumb | SEC发动机电子调节器开关  ON/OFF 备份系统转换开关 |
| `524` | `3026` | default_2_position_tumb | A/B ON/OFF 加力切断开关 |
| `525` | `3027` | default_2_position_tumb | A/SURGE 开关ON/OFF 防喘切断开关 |
| `561` | `3063` | default_2_position_tumb | 发动机空中启动开关盖 |

## FUEL（设备号 33）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `514` | `3016` | default_2_position_tumb | FEED油阀保险盖 |
| `515` | `3017` | default_2_position_tumb | FEED油阀 on/off |
| `516` | `3018` | default_2_position_tumb | 油阀保险盖 |
| `517` | `3019` | default_2_position_tumb | 油阀active /OFF |
| `518` | `3020` | default_2_position_tumb | start油泵 直流电动泵开关 |
| `564` | `3066` | default_3_position_tumb | AAR开关 |

## MISC（设备号 38）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `537` | `3039` | default_2_position_tumb | 信号弹发射保险盖 |
| `538` | `3040` | default_push_button | 信号弹发射按钮 |
| `539` | `3041` | default_2_position_tumb | 应急液压泵开关 |
| `540` | `3042` | default_2_position_tumb | SHARS捷联航姿开关 |
| `563` | `3065` | default_2_position_tumb | P.H. 检测 |

## UFCP（设备号 46）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `728` | `3230` | default_axis_limited | HUD对比度调节旋钮 |
| `729` | `3231` | default_axis_limited | HUD亮度调节旋钮 |
| `730` | `3232` | default_2_way_spring_switch | 3档 + . - 瞬态步进开关 |
| `731` | `3233` | default_axis_limited | HUD备用光栅 |
| `732` | `3234` | default_axis_limited | UFCP亮度调节旋钮 |

## GEAR（设备号 32）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `502` | `3004` | default_2_position_tumb | 起落架超控按钮保护盖 |
| `503` | `3005` | default_2_position_tumb | 应急放轮 起落架超控按钮 |
| `504` | `3006` | default_axis_limited | 指示灯亮度 |
| `505` | `3007` | default_2_position_tumb | 起落架手柄 |

## ECS（设备号 30）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `941` | `3443` | multiposition_switch_limited | 12档旋钮供气温度选择旋钮 |
| `941` | `3443` | multiposition_switch | 12档旋钮供气温度选择旋钮 |
| `942` | `3444` | multiposition_switch_limited | 4档旋钮环控系统工作状态选择旋钮 |

## ELECTRIC_SYSTEM（设备号 1）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `904` | `3406` | default_2_position_tumb | 蓄电池开关 |
| `905` | `3407` | default_2_position_tumb | 主交流发电机开关 |
| `906` | `3408` | default_2_position_tumb | 直流发电机开关 |

## ZCP（设备号 37）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `541` | `3043` | default_2_position_tumb | 弹射座椅启动销秘 |
| `542` | `3044` | default_2_position_tumb | 销秘控制按钮盖 |
| `543` | `3045` | default_push_button | 销秘控制按钮 |

## ACP（设备号 29）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `938` | `3440` | default_axis_limited | COM2电台2音量旋钮 |
| `940` | `3442` | default_axis_limited | MSL 导弹音量旋钮 |

## SMS（设备号 16）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `506` | `3008` | default_2_position_tumb | 地面丢挂载开关 地面允许投放开关 |
| `507` | `3009` | default_2_position_tumb | panic保险盖 |

## WARNING_SYSTEM（设备号 5）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `901` | `3403` | default_axis_limited | 告警面板灯亮度调节旋钮 |
| `903` | `3405` | default_axis_limited | 氧气示流器亮度调节旋钮 |

## AAP（设备号 7）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `909` | `3411` | default_axis_limited | 亮度调节旋钮 |

## INS（设备号 18）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `908` | `3410` | multiposition_switch_limited | INS 3档旋钮惯导工作模式选择开关 |

## WCS（设备号 11）

| 元素ID | 命令号 | 类型 | 说明 |
|---|---|---|---|
| `500` | `3002` | multiposition_switch_limited | WCSBACKUP 3档旋钮 SAIU备份开关 |

---

## 还没有的：雷达模式 / 航路点

这两类都在 **MFCD**（设备 47，99 个控件）和 **UFCP**（设备 46，33 个控件）上，
但它们的按钮**没有中文注释**，而且我们读不到 MFD 当前显示哪个页面。

盲点 OSB 的风险是切到别的页面上去，所以这部分要用「固定按键序列 + 你在旁边看着确认」
的方式一个个试出来，不能靠猜。

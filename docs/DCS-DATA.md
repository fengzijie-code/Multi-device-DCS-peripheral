# DCS 能给什么数据（JF-17 实测）

> 实测时间：2026-11-12 23:52 · 机型 JF-17 · DCS 稳定版
> 方法：`dcs/Export.lua` 里的结构探针，进座舱后第 60 帧把 26 个接口全抓一遍
> 原始数据：`Saved Games\DCS\Logs\dcsprobe.json`
>
> **这份文档取代一切「我觉得应该能读到」的猜测。** 下面每一个「有/没有」都是实测的。

---

## 一、结论先说

| 类别 | 结果 |
|---|---|
| 飞参（速度/姿态/高度） | ✅ 全有 |
| 机体状态（起落架/襟翼/舵面） | ✅ 全有，**JF-17 有舵面偏度** |
| 载荷（挂什么弹、剩几个） | ✅ 有，还能读到**当前选中挂点** |
| 雷达开关状态 | ✅ 有（藏在 `SelfData.Flags.RadarActive`） |
| **锁定目标 / 距离 / 雷达模式** | ❌ **全都读不到** |

**最遗憾的一条**：`LoGetRadarInfo` 这个函数在你这个 DCS 版本里**根本不存在**（不是返回空，是函数都没有）。`LoGetLockedTargetInformation` / `LoGetTargetInformation` / `LoGetSightingSystemInfo` 三个函数存在，但**一律返回 nil**。

所以「战斗页显示锁定距离」这个想法，**做不到**。别在这上面花时间了。

---

## 二、能读到的（按用途分三类）

### A. 飞参 —— 已经在用

| 字段 | 实测值 | 单位 | 说明 |
|---|---|---|---|
| `IndicatedAirSpeed` | 172.041 | m/s | 面板自己换算成 kt |
| `AltitudeAboveSeaLevel` | 4997.76 | m | |
| `AltitudeAboveGroundLevel` | 4326.03 | m | |
| `VerticalVelocity` | −2.88 | m/s | |
| `AngleOfAttack` | 1.076 | 弧度 | |
| `MachNumber` | 0.692 | — | |
| `AccelerationUnits` | `{x,y,z}` | g | 取 y 就是过载 |
| `SelfData.Pitch / Bank / Heading` | 0.006 / −0.002 / 3.466 | 弧度 | |

### B. 机体状态 —— 部分在用

`LoGetMechInfo()` 有 8 项：

| 字段 | 结构 | 用途 |
|---|---|---|
| `gear` | `{value, status, nose.rod, main.left.rod, main.right.rod}` | `rod` 是 0–1 收放进度，**能做「正在收起 60%」** |
| `flaps` | `{value, status}` | 已在用 |
| `speedbrakes` | `{value, status}` | 已在用 |
| `canopy` | `{value, status}` | 已在用（0 = 关闭） |
| `wheelbrakes` | `{value, status}` | 已在用 |
| `parachute` | `{value, status}` | 减速伞，未用 |
| `refuelingboom` | `{value, status}` | 软管加油，未用 |
| **`controlsurfaces`** | `{eleron{left,right}, elevator{left,right}, rudder{left,right}}` | **JF-17 有数据！配平估读可用** |

> `controlsurfaces.elevator` 实测 `left = 0.0528 / right = 0.0517`（弧度）。左右不等说明有配平偏置。
> **这是第一个能读出舵面偏度的机型** —— TF-51D 和 Su-25T 都是 `null`。配平卡在 JF-17 上终于有意义了。

### C. 载荷与武器 —— 全新发现

`LoGetPayloadInfo()`：

```json
{
  "CurrentStation": ...,      // ← 当前选中的挂点（关键！）
  "Cannon": {...},
  "Stations": [
    {"CLSID": "DIS_PL-5EII",       "count": 1, "container": false},
    {"CLSID": "DIS_SD-10_DUAL_L",  "count": 2, "container": true},
    {"CLSID": "DIS_SPJ_POD",       "count": 1, "container": false}
  ]
}
```

- `CLSID` 是弹种标识（`DIS_SD-10_DUAL_L` = 左侧双联 SD-10）
- `count` 是剩余数量

> **`CurrentStation` 和 `Stations` 是两件事，别搞混（踩过这个坑）：**
>
> | 字段 | 含义 | 什么时候有值 |
> |---|---|---|
> | `CurrentStation` | **当前选中哪个武器站** | 按过武器切换键之后。实测刚进任务是 `0`（没选） |
> | `Stations` | **挂载清单**，这架飞机带了什么 | 任务加载后就定死，一直有 |
>
> 我第一次只读了 `CurrentStation`，于是「挂了 2 枚 GBU 和 PL-5」在面板上显示成全空。
> 正确做法是读 `Stations` 拼成清单，`CurrentStation` 只用来标「现在用哪个」。
>
> `Cannon.shells` 是机炮余弹（实测 180 发）。
> 对单人驾驶来说这是刚需 —— 真实 HOTAS 上有武器状态灯，我们的手机没有。

### D. 额外捡到的

| 字段 | 实测 | 说明 |
|---|---|---|
| `SelfData.Flags.RadarActive` | `false` | **雷达开没开**，能做成指示灯 |
| `SelfData.Flags.Jamming` | `false` | 自己被干扰 |
| `SelfData.Flags.IRJamming` | `false` | |
| `SelfData.UnitName` | `"新呼号"` | 玩家呼号 |
| `SelfData.Type` | `{level1..4}` | 机型标识，**能用来做机型自适应** |

---

## 三、读不到的（别再试了）

| 接口 | 状态 | 含义 |
|---|---|---|
| `LoGetRadarInfo` | **`__missing__`** | 函数不存在 |
| `LoGetLockedTargetInformation` | `__nil__` | 有函数，返回空 |
| `LoGetTargetInformation` | `__nil__` | 同上 |
| `LoGetSightingSystemInfo` | `__nil__` | 同上 |
| `LoGetNavigationInfo` | `__nil__` | 同上 |
| `LoGetRoute` | `__nil__` | 同上 |
| `LoGetCameraPos` / `CockpitInfo` / `FlightInfo` / `MissionTime` / `AngleOfSlide` | `__missing__` | 函数不存在 |

**含义**：锁定距离、目标数量、雷达模式（TWS/RWS/STT）、导弹告警方向 —— 全部拿不到。
想要这些只能上 **DCS-BIOS**（读内存，需要每机型适配文件），那是另一个量级的工程。

---

## 四、单位有三个陷阱（会导致面板显示假数据）

| 字段 | Su-25T | JF-17 | 后果 |
|---|---|---|---|
| `fuel_internal` | 3170.88（kg） | **0.999994（比例）** | 面板已有自适应，OK |
| `Temperature.left` | 664.07（°C） | **0.72334（比例？）** | ⚠️ **面板现在会显示「1 °C」，是错的** |
| `HydraulicPressure` | 210（有值） | **0 / 0** | ⚠️ 面板显示「0」，但 JF-17 压根没这个传感器，应该是「--」 |

**`fuel_internal` 说明**：JF-17 满油约 2400 kg，但接口只给比例，**换算不出公斤**。所以面板只能显示百分比 —— 这是硬限制，不是我们偷懒。

**`HydraulicPressure = 0` 的歧义**：分不清「压力真的是 0」还是「这机型没这个数据」。Export API 的缺陷，只能靠机型白名单绕过。

---

## 五、由这批数据能做什么（按价值排）

1. **战斗页显示当前武器 + 剩余数量**（`CurrentStation` + `Stations`）
   —— 单人驾驶最缺的就是这个。真实 HOTAS 有武器灯，我们只能靠屏幕，但至少不用切 MFD。
2. **雷达开关指示灯**（`Flags.RadarActive`）
   —— 一个小圆点，比翻 MFD 快。
3. **配平卡复活**（`controlsurfaces`）
   —— JF-17 有舵面偏度，之前对 TF-51D/Su-25T 的判断在这里不成立。
4. 起落架收放进度（`gear.*.rod`）
   —— 「正在收起 60%」比「运动中」更有信息量。优先级最低。

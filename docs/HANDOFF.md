# 交接文档

> 给接手这个项目的 AI。读完之后你应该能直接干活，不需要再问用户任何背景问题。
> 最后更新：2026-11-13 凌晨

---

## 一、这是什么

一个**把手机和 iPad 变成 DCS 飞行外设**的项目。用户单人飞 **JF-17**（偶尔 Su-25T / TF-51D）。

- **Pixel 6a**：当摇杆。手机倾斜 → 杆量，滑动 → 油门，USB 连 PC
- **iPad**：当仪表盘 + 座舱控制面板，走 Wi-Fi
- **PC（Windows）**：跑桥接服务，把手机输入转成 vJoy 轴/按钮，把 DCS 数据转成 HTTP 给 iPad

**用户的工作节奏**：经常凌晨干活，要求直接、讨厌铺垫、会直接骂人。他要的是「能飞」，不是漂亮的架构。**先给证据再动手，别猜。**

---

## 二、现在什么能用（别弄坏）

| 功能 | 状态 | 入口 |
|---|---|---|
| 手机摇杆（起降页） | ✅ 稳 | 杆/油门/脚舵/襟翼/起落架/配平/减速板/机轮刹车 |
| 手机摇杆（战斗页） | ✅ 稳 | 油门/绿点盘（贴油门右侧）/紧凑的武器切换·锁定·干扰弹/**右上角：机炮 + 武器投放**/**脚舵（最底）** |
| 视角（看座舱外） | ✅ 由头瞄负责 | 头瞄（head tracking）；v1.2.0 起手机端视角轴已移除 |
| iPad 三栏显示 | ✅ 稳 | 战斗/巡航/降落，1Hz 轮询 |
| **iPad 反向控制座舱** | ✅ 可用 | 起落架/襟翼/减速伞/着陆灯/加油探管/应急液压泵 |
| **iPad 操作 MFD** | ✅ 刚做完，待真机确认 | MFD 标签页：键上直接标出它此刻的功能，页面跟着按键自动跳 |

**验证入口**：`curl http://127.0.0.1:8080/state` 能看到全部数据就说明主链路正常。

---

## 三、架构（三条数据流）

```
① 遥测：DCS ──LoGet*──> Export.lua ──UDP:5010──> beacon.py ──HTTP /state──> iPad / Pixel
        60Hz 主帧 + 1Hz 慢变量包

② 操纵：Pixel ──HTTP POST /input──> beacon ──> vjoy_out.py ──> vJoy ──> DCS
        手机倾斜→vJoy 轴，按钮→vJoy 按钮位图

③ 座舱：iPad ──HTTP POST /cmd──> beacon ──写文件──> Export.lua ──> performClickableAction
        绕开 DCS 的按键绑定系统，等价于鼠标点座舱开关
```

**为什么 ③ 用文件不用 UDP**：UDP 端口确实被 DCS 绑定了，但 `receive()` 在 Lua 沙盒里收不到数据。文件通道（`dcs_cmd.txt`）是唯一验证可用的。

---

## 四、关键文件

| 文件 | 作用 | 注意 |
|---|---|---|
| `dcs/Export.lua` | DCS 侧全部逻辑 | **改了必须重启任务才生效** |
| `tools/beacon.py` | HTTP 服务、UDP 收遥测、/cmd 转发 | 主入口，`/state` `/panel` `/cmd` `/input` |
| `tools/vjoy_out.py` | 写 vJoy 轴和按钮 | `MAX_BTN = 30` |
| `tools/run-all.py` | 启动器（等设备、建隧道、拉服务） | 被 `start-usb.bat` 调用 |
| `tools/panel.html` | iPad 页面：仪表三栏 + MFD 标签页 | 按 mtime 缓存，**改完刷新即生效** |
| `android/.../YokeController.kt` | 手机端核心：倾斜→轴、按钮、配平 | `BUTTON_COUNT = 30` |
| `android/.../ui/YokeScreen.kt` | 起降页 + 按钮编号常量 `YokeBtn` | |
| `android/.../ui/CombatScreen.kt` | 战斗页 | |
| `android/.../ui/Controls.kt` | `LockChip` / `GuardButton` / `TrimButton` | 防误触组件都在这 |
| `tools/install-apk.py` `.bat` | 装 APK 到手机 | 双击 .bat |
| `tools/watch-state.py` | 实时盯数据，一眼看出卡在哪一跳 | 调试神器 |

**文档**（都在 `docs/`）：`PANEL.md` 仪表盘、`YOKE.md` 摇杆、`BINDING.md` 绑键表、`DCS-DATA.md` 数据实测、`JF17-CONTROLS.md` 68 个可控开关、`JF17-MFD.md` MFD 键位，`JF17-MFD-PAGES.md` 各画面键标签、`LAYOUT.md` 外设分工框架。

---

## 五、踩过的坑（**别再踩**）

1. **命令号 ≠ 元素 ID**。JF-17 的 `click_cmds` 从 3001 起递增：**`command = 元素ID + 2502`**。发 `505` 是错的，正确的是 `3007`。

2. **Lua 的 `local` 作用域从声明处开始**。变量定义在引用它的函数后面 → 读到全局 `nil`。为这个白排查了一整轮（`dbg` 永远是 null）。

3. **Lua 的 `and/or` 会吞掉 `false`**。`cond and flag or nil`，当 flag 是 `false` 时整个表达式变 `nil`。「雷达关着」被误报成「没这个数据」。要用显式 `if`。

4. **`d:method` 不能在条件里裸用**。`if d:performClickableAction then` 是语法错误，要写 `d.performClickableAction`。

5. **单元测试会打到生产路径**。`Export.lua` 在测试里跑到第 60 帧会触发结构探针，把夹具假数据写进真实 `Saved Games` 目录，而且文件一存在真机就不再抓。夹具里加了 `_TEST_ENV` 挡住。

6. **结构探针放在 `LuaExportStart` 没用**。那时座舱还没加载，`LoGet*` 全返回 nil。要等到进座舱后第 60 帧。

7. **`CurrentStation` 不是挂载清单**。它是「当前选中哪个武器站」，刚进任务是 `0`。挂载清单在 `Stations[]` 里。

8. **同名字段单位因机型而异**。`fuel_internal`：Su-25T 给公斤（3170），JF-17 给比例（0.999）。`Temperature`：Su-25T 给摄氏度（664），JF-17 给比例（0.72）——后者换算不出温度，发 `null` 别发假数。

9. **DCS 读不到的**：`LoGetRadarInfo` 函数根本不存在；`LockedTargetInformation` / `TargetInformation` / `SightingSystemInfo` 一律返回 nil。**锁定距离、目标数量、雷达模式全都拿不到**，除非上 DCS-BIOS。

10. **adb 会僵死**。进程在、5037 在监听、客户端连上去永远不返回。只能 `taskkill /F /IM adb.exe`（`adb kill-server` 没用，它也要先连上那个死掉的服务）。

11. **vJoy 按钮数改了必须重启 DCS**。它只在启动时枚举设备，否则新按钮在绑定界面里根本不出现。

12. **`clickabledata.lua` 里没有键名，`command_defs.lua` 里才有**。MFD 那 99 条定义在 clickabledata 里长得一模一样（只有 ID 不同），照它只能靠猜；翻到 `command_defs.lua` 的 `cmd_names`，`"Left MFCD D3"` 这种名字是明写的。**以后找任何座舱控件的语义，先去 cmd_names 搜**。

---

## 六、怎么调试（按这个顺序）

```bash
# 1. 一眼看出卡在哪一跳
python tools/watch-state.py            # 无主帧 / 有主帧无慢变量 / 全通

# 2. 看原始数据
curl http://127.0.0.1:8080/state

# 3. DCS 侧日志（Export.lua 的所有 log_info/log_error 都在这）
grep -a "反向通道\|探针\|座舱命令" "C:/Users/lenovo/Saved Games/DCS/Logs/dcs.log" | tail

# 4. 发一条座舱命令并看回执
curl -X POST -d '{"dev":32,"cmd":3007,"val":0}' http://127.0.0.1:8080/cmd
# 然后读 /state 的 dbg 字段：
#   32:3007:D  设备拿到、方法调用了
#   32:3007:N  GetDevice 返回空（设备号不对）
#   32:3007:M  设备有但没有 performClickableAction
```

**改 `Export.lua` 之后必须让用户重启任务**；改 `panel.html` 只需刷新浏览器。

---

## 七、下一步该做什么


### 0. 【已解决】MFD 页面状态可以直接读 —— 不用截图、不用 OCR

DCS 有官方的指示器接口，Export.lua 里直接能调：

```lua
list_indication(indicator_id) -> string   -- 该指示器当前页的全部元素文本
```

JF-17 三块 MFD 的指示器编号是 **8 / 9 / 10**（左 / 中 / 右）。实测 dump 里能直接看到
`RDR`、`RWS`、`IFF`、`CNTL`（中屏雷达页）、`HSD`、`CLNK`、`TRU`（右屏）、`adi_*` 元素名（左屏 EFIS）。

**页面识别靠元素名而不是文字**：文字会带上一页的残留，元素名（`rdr_aa_*` / `adi_*` / `wpt_*`）
是页面脚本里静态定义的，只属于当前页。`tools/gen-mfd-pages.py` 会把每个页面的元素名
抽出来写进 `tools/mfd-pages.json`（字段 `e`），面板按「元素名前缀命中数 / √(页元素数)」打分选页。

Export 每秒调一次 `list_indication(8/9/10)`，只留元素名（≤40 个，去掉 `osb_txt`），
放进 sys 包的 `mfd` 字段（`L=…|C=…|R=…`）。**这是权威来源** —— 键盘快捷键切页也能跟上，
因为它读的是屏幕内容，不是按键动作。

顺带记下同一次普查里确认可用的接口：
`GetIndicator(i)`（方法：`set_page` / `assign_dedicated_viewport` / `get_dedicated_viewport`）、
`c_indication_txt_equal_to`、`a_cockpit_perform_clickable_action`、`LoGetAircraftDrawArgumentValue`。

**踩过的弯路（别再走）**：`LoGet*` 45 个函数里没有任何 MFD 相关；50 个设备没有一个支持
`get_argument_value`（只有 `GetDevice(0)` 有座舱参数）；截屏 + OCR 虽然可行（`tools/mfd-read.py`
已实现、`MFD_tap.lua` 视口配置也写了），但它是**兜底方案**，不是首选。

### 1. MFD 操作 —— 键位和页面标签都已从代码挖出，只剩「进座舱核对一遍」

**两条关键线索，都是代码里明写的，别再靠试：**

1. **哪个 ID 是哪颗键** → `command_defs.lua` 第 743–830 行的 `cmd_names`
   （`PNT_762 = "Left MFCD D3"`）。三块屏 × 33 键的 ID/命令号表在 `docs/JF17-MFD.md` 第三节。
   要点：`dev = 47`（MFCD），`cmd = ID + 2502`，按钮 `val=1`，Power 是两档开关 `1`/`-1`。
2. **每个画面上每颗键写的是什么** → `Cockpit/Scripts/MFCD/Indicator/*.lua`，
   这就是 MFD 画面的绘制代码，键标签是 `{value="XXX", cx=…, cy=…}`，坐标常量直接对应物理键。
   `python tools/dump-mfd-pages.py` 导出全部 61 个页面 → **`docs/JF17-MFD-PAGES.md`**。

已经确定的：主菜单（D3）是 `U1 RDR / U2 INS / U3 TACAN / U4 APR / U5 POD`、
`L1 HSD / L2 EFIS / L3 CLNK / L4 DATA`、`R1 SMS / R2 CMBT / R3 BIT / R4 CHKLS / R5 PFL`；
雷达页左列是搜索参数（`L3`=方位角、`L5`=扫描行数、`L4`=天线稳定）；**切雷达模式 = 雷达页按 U1**
（手册图注 A + 模式菜单页 `L1–L5`=条目 1–5、`R1–R5`=条目 6–10）。

**已经做完的**：`panel.html` 有 MFD 标签页，三块屏切换 + 34 个按钮，**每个键上写的就是它此刻在屏幕上的字**
（`L3 60` / `L5 4BR` / `U5 CNTL`），页面跟着按键自动跳（D3 主菜单、D2/D4 快切、主菜单→各页），
对不上时用「当前画面」下拉框改。数据由 `python tools/gen-mfd-pages.py` 从 DCS 脚本生成，不要手改那段。

**明天要做的**：`docs/JF17-MFD.md` 第七节有 9 步实测清单（每步带预期，对不上才是新闻）。
真正的新信息只有两条：**U1 模式菜单里 10 个条目分别是什么**、**CNTL 菜单里 L/HST/DCLT 对应 R 几**。

**永远解决不了的**：MFD 画面内容 DCS 不导出（`LoGet*` 没有 MFD 接口），所以「此刻屏幕显示什么」拿不到 —— 但「按键是什么、页面上有什么标签」现在全是代码级确定的。

### 2. 其他待办

- 战斗页还没接 `TWS/RWS` 切换、目标切换（按钮 7-9 已预留，等 MFD 通了再说）
- iPad 座舱按钮只有 6 个，`docs/JF17-CONTROLS.md` 里还有 68 个可用
- 配平卡在 JF-17 上可用（`controlsurfaces` 有数据），但只在手机起降页，iPad 没显示

---

## 八、用户的操作习惯（照着做）

- **启动**：双击 `tools\start-usb.bat`。开机后只需要这一个
- **装 APK**：双击 `tools\install-apk.bat`（**别让他手敲 adb**，他试过，卡住了会烦）
- **iPad 地址**：`http://<PC的局域网IP>:8080/panel`，需要先开 Windows 移动热点（iPad 连热点，PC 的地址通常是 `192.168.137.1`）
- 热点连不上时：**把热点频段钉到 2.4GHz**（校园网在 DFS 信道上时 iPad 会拒绝关联）

**沟通要点**：给结论、给证据、别解释太多。他问「为什么」，要能从原理讲到数字。

---

## 九、2026-11-13 全量回归（本次改动，接手先看这条）

跑了一遍脱离真机的完整闭环测试：`tests/integration_test.py`（Chrome 模拟 iPad + 嵌入 Lua 跑真实 `Export.lua` + 隔离的 beacon）。
首轮 66/82，定位 12 个缺陷，修完 **82/82 全绿**；`tests/test_export_lua.py` **42/42**。
计划 / 结果 / bug / 修改计划分别在 `docs/TEST-PLAN-CURRENT.md`、`TEST-REPORT.md`、`BUG-LIST.md`、`FIX-PLAN.md`。

**这次改了什么（都影响行为，别当普通重构）**：

- `tools/beacon.py`：拒收 NaN/Inf 与畸形慢变量（以前一个坏包就能打死 UDP 监听线程）；
  `/cmd` 校验 dev/cmd/val 并改成定点小数；命令文件加「等上一个被消费」的单槽锁，连发两条不再丢。
- `dcs/Export.lua`：**真机结构下 `gr`（gear.nose.rod）和 `cs_a/cs_e/cs_r`（`{left,right}`）以前全是 null**，
  现在能读到；设备调用失败不再伪报 `D0` 成功回执。→ **改了 Export.lua，真机必须重启任务才生效。**
- `tools/panel.html`：屏幕回传不再把 `DOWN_` 页写进上半区；座舱按键跳页会落盘；
  页面刷新不再重放历史按键（以前一刷新页面就跳）。
- 工具链：`mfd-audit.py` 的 D3 双重偏移、`check-panel.py` 取 `h2`、`vjoy_out.py` 心跳 `//vjoy`、单测缺 `ufcp` 字段，全部修掉。

复现就一条：`python tests/integration_test.py`（约 1 分钟，自动起隔离端口 8091/5091，不碰 8080/5010，不写真实 Saved Games）。

**真机也验过了（14:44 用户重启 USB + 任务后）**：`python tests/live_dcs_test.py --probe-version` → **11/11**。
新版 `Export.lua` 已备份部署到 `Saved Games/DCS/Scripts/`（备份 `Export.lua.bak-20261113-144040`）。
真机上 `sys.gr` 从 `null` 变成 `0.0`、`sys.cs_e` 有实时数值（这就是 BUG-04 修好的直接证据），
`POST /cmd val=NaN` 返回 400（BUG-05 修好）。报告在 `docs/TEST-REPORT-LIVE.md`。
以后再改这三个文件，记得「改完 ≠ 生效」：Export 要重进任务、beacon 要重启桥接、panel 刷新即可。

**手机端战斗页也补了（20:15）**：用户指出「没有脚舵、不能转视角」。根因不是没实现，
是 `CombatScreen` 砍了 `RudderBar`/`ViewPad`，且 `MainActivity` 没给战斗页接 `onView`
→ `vx/vy` 恒 0。现在中间列 = 杆位（自适应尺寸）+ 脚舵滑块 + 视角区，右列盲操按钮一个没挪。
`gradlew :app:compileDebugKotlin` / `assembleDebug` 均 BUILD SUCCESSFUL（JDK 在
`D:\Android Studio\jbr`，Gradle 9.9.0，`--offline` 可用），APK 已用
`python tools/install-apk.py` 装到 Pixel，真机触摸实测 `r` 峰值 0.729、
`vx=1.0`/`vy=0.833`、松手全回中。新增 T-STAT-010 静态守四个回调，离线回归 **83/83**。
详见 `docs/TEST-REPORT.md` 第七节。装 APK 前记得 `adb reverse tcp:8080 tcp:8080` 要在。

**20:25 微调**：用户反馈「视角太大，跟绿点指示一致就行」。`ViewPad` 原来是扁宽横条，
圆形绿点指示只占中间一小块；改成 **96dp 正方形居中**，圆内切容器。
映射半径仍是 `min(宽,高)/2-10 = 38dp`，拖多远算满舵不变。重新编译/打包/安装后
真机复验 `vx=0.847`、`vy=0.678`（拖 100/80px）、松手回中。截图 `.tmp/pixel-viewpad-square.png`。

**20:50 战斗页重排 → 20:53 / 20:57 两次更正（以最终版为准）**：初版把视角放
左上角（截图 `.tmp/pixel-combat-relayout.png`），用户随即更正「武器、机炮和视角
都放在右上角」，之后又要求把中间的校零/解锁键和 4 个按钮改小。**最终版面见文末
20:53/20:57 段**，截图 `.tmp/pixel-combat-compact.png`。

**按键核查有实质结论**：`docs/BINDING.md` 原本只有一个 `FIRE = 6`（BTN7），关键词把
`Trigger`（机炮扳机）和 `Release`（挂架投放）混写在一起 —— DCS 里这是两条独立命令，
一个按钮只能绑一条。按「不重排已有编号」：`BTN7` 语义收窄为**武器投放**，新增
`GUN_FIRE = 11` / `BTN12` 给**机炮**，7–9 预留位不动。`BINDING.md` 补了迁移步骤
（vJoy 按钮数 ≥ 12、重启 DCS、各机型把 `JOY_BTN7` 上的 Trigger 改绑 `JOY_BTN12`、
`BTN7` 改绑 Weapon Release），`YOKE.md` / `LAYOUT.md` 同步。

真机 `/input` 实测：**机炮 = bit11(2048)、武器投放 = bit6(64)，两键互不串**；
视角 `vx=0.854/vy=0.683`、脚舵 `r=0.456`，武器↑↓ bit3/4、锁定 bit5、干扰弹 bit10，
松手全 0。新增 `T-STAT-011` 静态守住编号与版面顺序；全量离线回归 **84/84**、单测 **42/42**。
详见 `docs/TEST-REPORT.md` 第 8 节。

> ⚠️ 改了 `BTN7` 的语义，**各机型在 DCS 里的绑定必须重绑一次**，否则打出去的
> 可能还是机炮。装完新 APK 只是手机侧生效。

**20:53 + 20:57 → 21:14 最终版面**：右上角一整组（列宽 220dp）= 视角 **160dp 正方形**
（`Alignment.CenterEnd` 靠右边缘、标签 13sp）+ 其正下方「机炮 / 武器」两个红色
250ms 长按键（**84dp 高、18/12sp 文字**）；绿点盘贴油门右侧；中间的解锁键收成
220×42dp，武器↑↓ / 锁定 / 干扰弹各 132×60dp 组成 2×2 紧凑组垂直居中；
中间留白处底部一行只读状态字；脚舵跨整宽压最底。给共享 `ArmButton` /
`ViewPad` / `GuardButton` 各加了可选参数（默认值不变，起降页与中间按钮不受影响）。

真机复验两轮：右上角版 `vx=0.843/vy=0.674`、`r=0.470`；最终紧凑版
`vx=0.834/vy=0.668`、`r=0.480`。两轮都是 **机炮 bit11(2048) / 武器投放 bit6(64)
互不串**，武器↑↓ bit3/4、锁定 bit5、干扰弹 bit10，松手 + 上锁全 0。
`T-STAT-011` 现在还守「视角靠右 / 绿点盘在视角左侧 / 中间按钮是固定小尺寸」，
左右位置或尺寸再被改回去都会被挡住。离线回归 **84/84**、单测 **42/42**。
详见 `docs/TEST-REPORT.md` 第 8 节。

**21:04 按键逻辑 / 绑定方式核查（只改文档，代码一行没动）**：查 DCS 安装目录
`Mods/aircraft/JF-17/Input/JF-17/joystick/default.lua` + `Cockpit/Scripts/command_defs.lua`
后发现 `BINDING.md` 原来的关键词（`Weapon Release` / `Trigger` / `Pickle`…）**在 JF-17
操控界面里根本搜不到**，实际叫 `S3: Weapon Launch` / `S4: Fire Main Gun` /
`S8: Change Weapons` / `T2_Backward: Countermeasures Dispense` / `T5_Press: Lock Target`。
已全部改正并标出「保持型（down+up, value 1/0）」与「脉冲型（down/pressed）」的绑定方式；
另记了三个坑：S3/S4 默认绑 `JOY_BTN2/1` 与襟翼撞车（点襟翼可能开火）、JF-17 只有
单向循环切武器、机炮要先在 SMS 页选 GUN + FEED 充弹。

**结论**：按钮状态机（btnHeld 位保持 + 120ms 最小脉冲 + 50Hz + 多点）能带这两类命令，
**单次开火可行**；但 250ms 门槛吞短点射、7–9 号仍是预留位（缺 ACM/解锁/子模式）、
视角与发射键同在右上角同一只手 —— **不足以支撑持续空战对抗**。
待拍板的三项改动（门槛降到 120ms / 启用 7–9 / SMS 补机炮入口）见 `docs/BINDING.md` §九。

**21:14 右上角三个控件放大（用户：机炮/武器/视角太小，尤其视角）**：右列 150→220dp、
视角 96→160dp 正方形、发射键 60→84dp 高、文字 13/10→18/12sp、视角标签 10→13sp；
中间那组保持 20:57 缩小后的尺寸不动。视角映射半径随尺寸从 38→70dp
（`min(宽,高)/2-10`），拖满舵行程变长、控制更细，松手回中不变。

先试过 **168dp**，真机截图发现右下角两行状态字被挤成 0 高（右列 168+5+84=257dp
> 主体约 256dp）。改成 160dp 并把状态合并成**一行**挪到中间留白处，截图确认三个
控件都大、状态字完整、无重叠无截断。截图 `.tmp/pixel-combat-bigview-final.png`。

真机 `/input` 复验：视角拖 165/120px → `vx=0.825/vy=0.600`，脚舵 `r=0.480`；
**机炮 bit11(2048) / 武器投放 bit6(64) 互不串**，武器↑↓ bit3/4、锁定 bit5、
干扰弹 bit10；松手 `vx/vy/r=0`、上锁后五轴全 0。新增 `T-STAT-012` 守住放大后的
尺寸与字号，全量离线回归 **85/85**、单测 **42/42**。详见 `TEST-REPORT.md` 第 8 节。

---

## 十、v1.00 已发布（23:45，**视角功能的最后一版**）

用户买了头瞄，下一版要移除视角，所以把当前状态固化成 **`v1.00`**：
`versionName = 1.00`（`versionCode = 1`）、App 标题改「DCS 外设 · v1.00」、
release 变体沿用 AGP 自带 debug keystore 签名（v2，可直接覆盖安装），
并加 `lint.checkReleaseBuilds = false` —— 否则 `--offline` 构建会被
`lintVitalAnalyzeRelease` 拉 `lint-gradle:32.5.1` 卡住（本机无缓存）。

产物 `release/v1.00/DCS-Peripheral-v1.00.apk`（8.4 MB，
SHA-256 `6396b97881ed8f459b2f61097ec051aa456890496baa999a3dc9be84093c6b0f`），
已真机安装验收：`versionName=1.00`、标题正确、战斗页全部控件在、链路 4 ms / 49.9 Hz。
构建命令 / 安装方式 / 已知限制见 `README.md` 的 v1.00 章节。
**tag 只打在本地，没有 push。**

**下一版（v1.2.0，已做）移除视角时要动的地方**（先列好，免得漏）：
Rx / Ry 两根轴（`YokeController` 发送、`vjoy_out.py` 映射、`BINDING.md` §1）、
`ViewPad` 控件与战斗页视角区、`YokeSettings` 的视角横纵互换 / 两个反转开关、
`YOKE.md` 相关段落，以及 `T-STAT-010`（守 ViewPad + onView 回调）和
`T-STAT-012`（守 160dp 视角尺寸）两条静态检查。
—— 以上全部已在 v1.2.0 完成：`YokeController`/UI/校准页的视角代码删除，
`vjoy_out.py` 不再映射 Rx/Ry，`beacon.py` 回中列表去掉 vx/vy，测试改为守「视角已移除」。

---

### 十·补 v1.1.0 —— 补上 iPad 端，双端齐全（2026-11-14）

用户问「iPad 端和 Pixel 端都上传了没」：核查发现 v1.00 的 **git tag 里已含** iPad 端源码
（`tools/panel.html`、`dcs/Export.lua`、`tools/beacon.py` 等），但 `release/v1.00/`
只打了 Android APK，**没把 iPad 端作为发布产物打包**。本版补齐：

- `versionName` 升到 `1.1.0`、`versionCode` 升到 `2`、App 标题改「DCS 外设 · v1.1.0」
  （`android/app/build.gradle.kts`、`MainActivity.kt`）。Android 功能相对 v1.00 零变动。
- 新增 **iPad 端部署包** `release/v1.1.0/DCS-Peripheral-iPad-v1.1.0.zip`（95 KB，
  SHA-256 `e5f243d8b2583181f4d328ee536572e187fc553557e9ee571d7056a3b1cddb0f`）：
  含 `tools/`（panel.html + beacon/vjoy_out/usb-watchdog/run-all/mock_export + start-usb.bat
  + open-firewall.bat + mfd-pages.json）、`dcs/Export.lua`、部署说明 `DEPLOY.txt`
  （zip 根另置一份，解压第一眼可见）。
- Android APK `release/v1.1.0/DCS-Peripheral-Android-v1.1.0.apk`（8.1 MB，
  SHA-256 `ffa4d4309298865ffb9b62d7691cd2e2c904d422c85aa4b77ded489cea45fd1f`），
  同 v1.00 签名（v2 debug keystore）。

**验收**：iPad 端在本机做了端到端冒烟——`run-all --no-usb --no-vjoy --mock` 拉起 beacon +
watch + mock 三服务，`http://127.0.0.1:8080/state` 返回合法 JSON、`/panel` 返回 65 KB HTML
页面。Android 这边因为发布时 Pixel 没连上（`adb devices` 起服务卡死），**没对 v1.1.0 重跑真机
安装验收**；但代码仅改版本串，功能与已验收的 v1.00 完全一致，v1.00 结论仍有效。

**tag 仍只打在本地，没有 push。** 详见 `README.md` 的 v1.1.0 章节与包内 `DEPLOY.txt`。

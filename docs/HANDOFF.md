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
| 手机摇杆（起降页） | ✅ 稳 | 杆/油门/脚舵/襟翼/起落架/配平/视角 |
| 手机摇杆（战斗页） | ✅ 稳 | 武器切换/锁定/发射/干扰弹 |
| iPad 三栏显示 | ✅ 稳 | 战斗/巡航/降落，1Hz 轮询 |
| **iPad 反向控制座舱** | ✅ 可用 | 起落架/襟翼/减速伞/着陆灯/加油探管/应急液压泵 |
| MFD 操作（雷达模式/航路点） | ❌ **没做** | 见第七节 |

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
| `tools/panel.html` | iPad 页面 | 按 mtime 缓存，**改完刷新即生效** |
| `android/.../YokeController.kt` | 手机端核心：倾斜→轴、按钮、配平 | `BUTTON_COUNT = 30` |
| `android/.../ui/YokeScreen.kt` | 起降页 + 按钮编号常量 `YokeBtn` | |
| `android/.../ui/CombatScreen.kt` | 战斗页 | |
| `android/.../ui/Controls.kt` | `LockChip` / `GuardButton` / `TrimButton` | 防误触组件都在这 |
| `tools/install-apk.py` `.bat` | 装 APK 到手机 | 双击 .bat |
| `tools/watch-state.py` | 实时盯数据，一眼看出卡在哪一跳 | 调试神器 |

**文档**（都在 `docs/`）：`PANEL.md` 仪表盘、`YOKE.md` 摇杆、`BINDING.md` 绑键表、`DCS-DATA.md` 数据实测、`JF17-CONTROLS.md` 68 个可控开关、`JF17-MFD.md` MFD 键位、`LAYOUT.md` 外设分工框架。

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

### 1. MFD 操作（用户最想要的，卡在这里）

**已解决的部分**（`docs/JF17-MFD.md` 有全文）：每块屏 26 个周边键（U1-U5 / D1-D5 / L1-L8 / R1-R8）+ 四角 SYM/PWR/CONT/BRT。**键的功能随画面变化**，不是一键一义。

固定语义的几个：
- **D3** = 回上半区菜单（**撤销键，先打通这个**）
- **R8** = 下半区小菜单
- **U1** = 画面名称
- **D2** = 左 CMBT / 中 雷达 / 右 HSD
- **D4** = 左 SMS / 中 无 / 右 数据链（CLINK）

**卡在哪**：element ID（左 734-766 / 中 767-799 / 右 800-832）到键位（U1、D3…）的映射**无法从代码推断**——ID 连续但连续不代表按位置排列（741/774/807 是 toggle，打断了假设）。

**唯一办法是实测**，需要用户在场看着屏幕。步骤：
1. 让用户把中 MFD 切到雷达页
2. 先试 D3，找到它就等于有了撤销键
3. 再试 `740`（推断的 D2），猜对说明 ID 按位置排列
4. 然后试 `738`（U5，雷达控制菜单）

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

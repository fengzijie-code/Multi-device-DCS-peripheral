<div align="center">

# 多端 DCS 外设

**把 Pixel 手机变成摇杆，把 iPad 变成仪表盘和座舱控制面板。**

主打 JF-17 · 单人驾驶 · 不用买额外硬件

[![License](https://img.shields.io/badge/license-MIT-6fe3cb?style=flat-square)](LICENSE)
[![Release](https://img.shields.io/badge/release-v1.4.0-63c8ff?style=flat-square)](VERSIONS.md)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Android%20%7C%20iPadOS-ffb454?style=flat-square)](#-快速开始)
[![DCS](https://img.shields.io/badge/DCS%20World-JF--17-e33f92?style=flat-square)](docs/BINDING.md)

[快速开始](#-快速开始) · [界面](#-界面) · [文档](#-文档) · [更新日志](VERSIONS.md) · [许可](#-许可)

</div>

![iPad 输入端 · 起降页](docs/images/yoke-takeoff.webp)

---

## 📌 这是什么

一套本地跑的三件套：**PC 上三个 Python 进程**，加**一个单文件网页**。
手机或 iPad 打开网页就是操纵面，DCS 的遥测反向往回推。

- **不需要装 app 商店的东西**，iPad 端连安装都不用 —— Safari 打开、「添加到主屏幕」，就是一个全屏窗口。
- **不需要云**，所有数据在 127.0.0.1 和局域网里走。
- **不需要改 DCS**，只在 `Saved Games/DCS/Scripts/` 放一个 `Export.lua`。

### 三条链路

```
遥测   DCS ──UDP:5010──▶ beacon.py:8080 ──HTTP /state──▶ iPad / 手机
操纵   iPad ──HTTP /input──▶ beacon ──UDP:5011──▶ vjoy_out.py ──▶ vJoy ──▶ DCS
座舱   iPad ──HTTP /cmd──▶ beacon ──写文件──▶ Export.lua ──▶ 68 个座舱开关
```

实测 **50.0 Hz**、单帧 **3 ms**、看门狗 **531 ms** 回中。

---

## ✨ 特性

| | |
|---|---|
| **遥测下行** | `IAS / ALT / VS / AGL / HDG / G / MACH / AOA / RPM / FUEL`，50 Hz UDP，iPad 侧同时显示数字和姿态球 |
| **操纵上行** | 杆盘（触点浮动 + 位置亮点）、油门（保持）、脚舵（回中）、15 个按钮（含 TDC 四向），50 Hz |
| **安全兜底** | 默认上锁、按钮最短脉冲 120 ms、断线自动上锁、姿态异常兜底 —— 详见 [`docs/YOKE-IPAD.md`](docs/YOKE-IPAD.md) §4 |
| **手感可调** | 死区 / 行程 / expo 三参数 + 配平（force trim）+ 体感（陀螺仪）校零 |
| **一键启动** | 起服务前先查证书、端口、防火墙，起来后印**真实在听**的地址 |
| **两个端互不干扰** | `/input` 是同一个入口，手机和 iPad 可以混着用 |

---

## 🚀 快速开始

### 需要什么

| 必需 | 说明 |
|---|---|
| Windows PC | vJoy 只有 Windows 版，DCS 也在这台机器上 |
| [vJoy](https://sourceforge.net/projects/vjoystick/) 驱动 | 根目录 `vJoySetup.exe`，装一次。**Configure vJoy 里把按钮数设到 ≥ 15**，重启 DCS 生效 |
| DCS World + JF-17 | 绑键见 [`docs/BINDING.md`](docs/BINDING.md) §2 |
| iPad **或** Android 手机 | iPad 走 Wi-Fi（要装一次根证书）；手机走 USB 数据线 |

### 四步

**① DCS 侧** —— 把 `dcs/Export.lua` 复制到 `%USERPROFILE%\Saved Games\DCS\Scripts\`，重进任务。

**② 启动服务** —— 双击对应那个：

```bat
tools\start-ipad.bat     :: iPad 当杆：不需要手机、不建 adb 隧道
tools\start-usb.bat      :: 手机当杆：走 USB，自动建 adb 反向隧道
```

窗口里会逐条打预检结果，最后印出上手地址：

```
[证书] ✓ 有效，还剩 364 天，已含 2 个本机 IP
[端口] ✓ 8080 / 8443 / 5011 都空闲
[防火墙] ✓ 已有放行规则「DCS Peripheral Bridge」
──────────────────────────────────────────────
iPad 打开这一条（地址栏必须带 https://）
  https://192.168.1.42:8443/yoke
自检：http 200  ·  https 200
```

**③ 打开页面** —— 这台机器的地址，见上一步印出来的那一行。没有 DCS 想看效果就加 `mock`：

```bat
tools\start-ipad.bat mock     :: 60 Hz 假遥测，不要和真 DCS 同时开
```

**④ 加进主屏幕**（iPad）—— 分享 → 添加到主屏幕 → 从**桌面图标**启动。
这样才是没有地址栏的全屏窗口。首次要装一次根证书，步骤见 [`docs/YOKE-IPAD.md`](docs/YOKE-IPAD.md) §5。

> **只跑 iPad 那条路的话，Android 端可以完全不管** —— 不用装 APK，不用连数据线。

---

## 🎮 界面

玻璃 HUD 风格：不画面板，只有 1px 细描边、圆、小字距的浅色字。底图是 DCS 座舱，
任何实心色块都会立刻变成"网页控件贴在上面"，所以整页没有一个卡片底色。

<table>
<tr>
<td width="33%"><img src="docs/images/yoke-takeoff.webp" alt="起降页"><br><sub><b>起降</b> · 襟翼 / 起落架 / 减速板 / 轮刹</sub></td>
<td width="33%"><img src="docs/images/yoke-pfd.webp" alt="仪表页"><br><sub><b>仪表</b> · 姿态球 + 10 个数字</sub></td>
<td width="33%"><img src="docs/images/yoke-combat.webp" alt="战斗页"><br><sub><b>战斗</b> · 机炮 / 投放 / 雷达 / TDC</sub></td>
</tr>
</table>

版位是按**手位**排的，不是按好看排的：

| 位置 | 控件 | 为什么在这儿 |
|---|---|---|
| 中偏左 | 杆盘 | 左右手都能推，换页也不挪位 |
| 左·竖条 | 油门 | 左手大拇指自然落点，松手保持 |
| 右下角 | 脚舵 | 右手管杆盘 + 按钮 + 脚舵，和真机一致 |
| **左下角** | **解锁 / 已解锁（100 px 圆）** | 拇指落下去就够到，不用瞄 |
| 顶部 38 px 以下 | 状态行 / 页签 / 开关 | 让开 iPad 主屏的状态栏（时间、电量） |

---

## 📦 项目结构

```
android/          Android 摇杆 App（Kotlin + Compose，APK 在 release/）
tools/            PC 侧：beacon.py（桥接）、vjoy_out.py（vJoy 输出）、
                  yoke.html（iPad 输入端）、start.py（一键启动）、check-yoke.py（验收）
dcs/              Export.lua —— DCS 侧导出脚本
jf17-trainer/     座舱虚拟按键训练 + 冷启动流程（浏览器打开就能用）
docs/             文档（见下）
release/          按版本归档的 APK
```

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | **接手先读这个**：当前状态、架构、踩过的坑、下一步 |
| [`docs/YOKE-IPAD.md`](docs/YOKE-IPAD.md) | iPad 当杆：四页版面、手感、体感与证书、打不开怎么查 |
| [`docs/YOKE.md`](docs/YOKE.md) | 手机摇杆：页面、配平、USB 链路 |
| [`docs/PANEL.md`](docs/PANEL.md) | iPad 仪表盘：字段含义、三个硬限制 |
| [`docs/BINDING.md`](docs/BINDING.md) | vJoy 按钮/轴 ↔ DCS 功能对照表 |
| [`docs/DCS-DATA.md`](docs/DCS-DATA.md) | DCS 能读到什么、读不到什么（实测） |
| [`docs/JF17-CONTROLS.md`](docs/JF17-CONTROLS.md) | 68 个可远程操作的座舱开关 |
| [`docs/JF17-MFD.md`](docs/JF17-MFD.md) | MFD 周边键语义（U1 / D3 / R8…） |
| [`docs/LAYOUT.md`](docs/LAYOUT.md) | 外设分工框架：什么该上手机 |
| [`VERSIONS.md`](VERSIONS.md) | **版本历史**：每一版改了什么、为什么改 |

---

## 🧪 开发与验收

页面不是"看着差不多"就算完 —— `tools/check-yoke.py` 用 playwright + 系统 Chrome，
在 1194×834 的 iPad 横屏视口里**真的发触摸事件**（CDP `Input.dispatchTouchEvent`），
https 下还假造陀螺仪倾斜，然后回头查 `/input` 收到了什么：杆量、轴上是否有 `t`、
按钮 bit、切页后杆心是否挪位、元素有没有溢出视口。

```bat
:: 另起一套隔离端口，别和正在用的 8080 抢 /input
python tools\start.py --port 18080 --udp-in 15010 --tls-port 18443 --vjoy-port 15011 --no-vjoy mock

python tools\check-yoke.py https://127.0.0.1:18443/yoke   :: 74 项
python tools\check-yoke.py http://<本机IP>:18080/yoke      :: 70 项（必须用局域网 IP）
```

当前 **74 / 70 项全过**。

---

## 🚧 已知限制

- **只做横屏**。竖排明确不做 —— 竖起来时杆盘和按键都挤不下。
- **体感必须走 HTTPS**，而且要在 iPad 上装一次根 CA：iOS 不给明文页面的传感器数据。
  证书有效期受 iOS 限制（≤ 398 天），换网段后要重签 leaf（`start.py` 会自动发现）。
- **同时按下的点数贴着 iPad 上限**：推杆 + 油门 + 脚舵 + 按钮一起用时已经满了。
- **单人驾驶场景**，没做多端同步仲裁；两个端同时推会互相覆盖。

---

## 📄 许可

```
MIT License · Copyright (c) 2026 fengzijie
```

可以自由使用、修改、再分发、商用，只需保留版权与许可声明；**不提供任何担保**。
完整条文见 [`LICENSE`](LICENSE)。

仓库里还有两样**不在 MIT 范围内**的东西：

| 文件 | 归属 |
|---|---|
| `DCS JF-17 Thunder Guide.pdf` | 第三方参考资料，版权归原作者；仅作学习参考，不在 MIT 内 |
| `vJoySetup.exe` | 第三方安装包（vJoy，作者 Shaul Eizikovich）。**已被 `.gitignore` 排除，不在仓库里**，只在本地根目录方便安装 |
| DCS World / JF-17 模块 | 商标与版权归 Eagle Dynamics / Deka Ironwork 各自所有，本项目与其无隶属关系 |

要分发本项目，把上面那份 PDF 摘出去即可 —— 它不参与程序运行。

## 🙏 致谢

- [vJoy](https://sourceforge.net/projects/vjoystick/) —— 虚拟摇杆驱动，整条"操纵上行"的最后一步
- [DCS-BIOS](https://github.com/DCS-Skunkworks/DCS-BIOS) —— 调研座舱反向控制时的参照（GPL-3.0），本项目未直接使用其代码

---

<div align="center"><sub>Made for flying JF-17 with an iPad on the knee.</sub></div>

# 多端 DCS 外设

把 **Pixel 手机变成摇杆**、**iPad 变成仪表盘和座舱控制面板**，给 DCS World 用。
单人驾驶场景，主打 JF-17。

---

## 接手这个项目，从这里开始

**👉 [`docs/HANDOFF.md`](docs/HANDOFF.md)** —— 当前状态、架构、踩过的 11 个坑、下一步做什么，全在里面。

读完那一份就能直接干活，不需要再问背景。

---

## 一句话说清三条链路

```
遥测   DCS ──UDP:5010──> beacon.py:8080 ──HTTP /state──> iPad / 手机
操纵   手机 ──HTTP /input──> beacon ──> vjoy_out.py ──> vJoy ──> DCS
座舱   iPad ──HTTP /cmd──> beacon ──写文件──> Export.lua ──> 座舱开关
```

## 快速启动

```
tools\start-usb.bat        # 开机后只跑这一个
```

## v1.00 —— 第一个正式 release（2026-11-13）

> **这是保留「视角」功能的最后一版**：用户已购头瞄，下一版会移除视角轴、
> 战斗页视角区与相关文档。要留档或回滚就用 `v1.00` 这个 tag。

| 项 | 值 |
|---|---|
| Git tag | `v1.00` |
| `versionName` / `versionCode` | `1.00` / `1` |
| APK | [`release/v1.00/DCS-Peripheral-v1.00.apk`](release/v1.00/DCS-Peripheral-v1.00.apk)（8.4 MB） |
| SHA-256 | `6396b97881ed8f459b2f61097ec051aa456890496baa999a3dc9be84093c6b0f` |
| 签名 | APK Signature Scheme v2，AGP 自带 debug keystore（`CN=Android Debug`）。自用可直接覆盖安装；对外分发需换正式签名 |
| 构建 | `gradlew :app:assembleRelease --offline`（JDK `D:\Android Studio\jbr`） |
| 验收 | 离线闭环 **85/85**、Lua 单测 **42/42**、真机链路 **11/11**、功能层 VERIFY **5/5**；release 包真机安装/启动/战斗页全部通过 |

**这一版包含**：三条链路全通（遥测 / 操纵 / 座舱反向控制）；手机战斗页最终版面
（右上角 160dp 视角 + 机炮 / 武器双发射键、绿点盘贴油门、中间紧凑按钮组、脚舵最底）；
机炮 `JOY_BTN12` 与武器投放 `JOY_BTN7` 拆成两个独立按钮；iPad UFCP 四窗实时回传。

**安装**：`adb install -r release/v1.00/DCS-Peripheral-v1.00.apk`（或把文件发到手机上点装）。
装完按 [`docs/BINDING.md`](docs/BINDING.md) §2 在 DCS 里重绑 `BTN7` / `BTN12`，
并清掉 `S3` / `S4` 的默认绑定冲突 —— 不然点襟翼可能顺带开火。

**发布时已知的限制**（不阻塞 v1.00）：7–9 号仍是预留位（缺 ACM 格斗模式 / 目标解锁）
（缺 ACM 格斗模式 / 目标解锁）→ 单次开火可行，不足以持续空战对抗；
机炮需先在 iPad 的 SMS 页选 GUN + FEED 充弹；视角松手回中且与发射键同手。
详见 [`docs/BINDING.md`](docs/BINDING.md) §9 与 `docs/TEST-REPORT.md` 第 8 节。

> `.gitignore` 默认忽略 `*.apk`；v1.00 这一个发布包已用 `git add -f` 随 tag
> 一起入库，方便回滚时直接取包。后续版本若仓库体积变大可改走外部附件。

---

## v1.1.0 —— 补上 iPad 端，双端齐全（2026-11-14）

> **回答「iPad 端上传了没」**：v1.00 的 git tag 里其实**已经包含** iPad 端源码
> （`tools/panel.html`、`dcs/Export.lua`、`tools/beacon.py` 等都在仓库里），
> 但 `release/v1.00/` 只打了 Android APK，没有把 iPad 端作为发布产物打包。
> 本版把 iPad 端做成可直接部署的包，补齐双端。

| 项 | 值 |
|---|---|
| Git tag | `v1.1.0` |
| `versionName` / `versionCode` | `1.1.0` / `2`（仅版本号变更，Android 功能与 v1.00 一致） |
| Android APK | [`release/v1.1.0/DCS-Peripheral-Android-v1.1.0.apk`](release/v1.1.0/DCS-Peripheral-Android-v1.1.0.apk)（8.1 MB） |
| APK SHA-256 | `ffa4d4309298865ffb9b62d7691cd2e2c904d422c85aa4b77ded489cea45fd1f` |
| **iPad 端部署包** | [`release/v1.1.0/DCS-Peripheral-iPad-v1.1.0.zip`](release/v1.1.0/DCS-Peripheral-iPad-v1.1.0.zip)（95 KB） |
| iPad 包 SHA-256 | `e5f243d8b2583181f4d328ee536572e187fc553557e9ee571d7056a3b1cddb0f` |
| 签名 | 同 v1.00：APK Signature Scheme v2，AGP 自带 debug keystore |
| 构建 | `gradlew :app:assembleRelease --offline`（JDK `D:\Android Studio\jbr`） |
| 验收 | **iPad 端本地冒烟通过**：`run-all --no-usb --no-vjoy --mock` 起 3 个服务，`/state` 返回合法 JSON、`/panel` 返回 65 KB HTML 页面；Android 与 v1.00 功能一致（仅版本串变更） |

**这一版包含**：
- **Android 端**：同 v1.00 全部功能，仅 `versionName` 升到 `1.1.0`、`versionCode` 升到 `2`、App 标题改「DCS 外设 · v1.1.0」。
- **iPad 端部署包**（解压即用）：`tools/panel.html`（单文件页面）+ PC 桥接三件套
  （`beacon.py` HTTP:8080、`vjoy_out.py` 虚拟摇杆、`usb-watchdog.py` USB 隧道看守）+
  `start-usb.bat` 一键启动 + `mock_export.py` 假遥测 + `dcs/Export.lua`（DCS 侧导出脚本）+
  部署说明 `DEPLOY.txt`。

**iPad 端安装**（详见包内 `DEPLOY.txt`）：① 把 `dcs/Export.lua` 复制到
`C:\Users\<你>\Saved Games\DCS\Scripts\Export.lua` 并重进任务；② 双击 `tools\start-usb.bat`；
③ iPad 连同一局域网，Safari 打开 `http://<PC局域网IP>:8080/panel`。
没有 DCS 时跑 `start-usb.bat mock` 看假数据。

**Android 端安装**：`adb install -r release/v1.1.0/DCS-Peripheral-Android-v1.1.0.apk`
（旧 v1.00 可直接覆盖）。装完同样按 [`docs/BINDING.md`](docs/BINDING.md) §2 重绑。

> **本版验收说明**：发布时 Pixel 未连接（`adb devices` 起服务卡死），故未对 v1.1.0 的 APK
> 重跑真机安装验收；但 Android 代码相对 v1.00 仅改版本串、功能零变动，v1.00 的真机验收结论
> 仍然有效。iPad 端则在本机完成了端到端冒烟（beacon 服务 + mock 遥测 + 页面可达）。

---

## v1.2.0 —— 移除手机端视角轴（2026-11-14）

> **触发**：用户买了头瞄（head tracking），手机端的「视角」拖拽区不再需要。
> 这一个版本把视角轴**整条链路**拿掉：手机 UI 的视角区、`YokeController` 的视角
> 发送段、校准页三个视角开关、PC 端 `vjoy_out.py` 的 `Rx/Ry` 视角轴映射、
> `beacon.py` 的回中类列表，以及守住这些的静态测试（T-STAT-010/011/012、T-IN-003）。
> 详见 `docs/HANDOFF.md`「下一版移除视角」一节。

| 项 | 值 |
|---|---|
| Git tag | `v1.2.0` |
| `versionName` / `versionCode` | `1.2.0` / `3` |
| Android APK | `release/v1.2.0/DCS-Peripheral-Android-v1.2.0.apk`（构建后生成） |

**这一版包含**：
- **Android 端**：移除战斗页右上角视角区、起降/校准页的视角相关控件；战斗页右列
  现在只剩「机炮 / 武器投放」两个发射键。**视角交给头瞄**。
- **PC 桥接端**：`vjoy_out.py` 不再占用 vJoy 的 `Rx/Ry` 轴，空出来给头瞄直接用
  （头瞄和手机不再抢同一对轴，也不会被桥接的「回中」每帧拉回正中）。

**保留**：`v1.00` 的 git tag 仍可作「含视角」的回滚点。`vJoy` 的 `Rx/Ry` 若头瞄
不用，也可在 Configure vJoy 里关掉，不影响手机其余轴。构建命令同前：
`gradlew :app:assembleRelease --offline`（JDK `D:\Android Studio\jbr`）。

---

## v1.3.0 —— 起降页新增减速板与机轮刹车（2026-11-14）

> **触发**：用户要在手机起降页直接控制减速板和机轮刹车，不必再伸手动座舱开关。
> 这两个都是起降构型操作，延续「襟翼↑↓ / 起落架」的两键 + 保持型按钮模式，
> 按钮位直接透传到 vJoy，控制器 / 桥接端无需改动。

| 项 | 值 |
|---|---|
| Git tag | `v1.3.0` |
| `versionName` / `versionCode` | `1.3.0` / `4` |
| Android APK | `release/v1.3.0/DCS-Peripheral-Android-v1.3.0.apk`（构建后生成） |

**这一版包含**：
- **Android 端**：起降页在「襟翼 / 起落架」那一行下方新增一行三个按钮 ——
  **减速板开 / 减速板收**（按下型两键，对应 DCS `Speed Brake Extend` / `Retract`）、
  **轮刹**（保持型，按住=刹车、松手=释放，对应 DCS `Wheel Brake`）。
- **按钮编号**：沿用不重排原则，新增 `BTN13 / BTN14 / BTN15`（代码 `YokeBtn` 常量
  `SPEED_BRAKE_OPEN=12` / `SPEED_BRAKE_CLOSE=13` / `WHEEL_BRAKE=14`）。
- **DCS 绑键**：按 [`docs/BINDING.md`](docs/BINDING.md) §2 新增三行，vJoy 按钮数需 ≥ **15**（Configure vJoy 里改，重启 DCS 生效）。

**安装**：`adb install -r release/v1.3.0/DCS-Peripheral-Android-v1.3.0.apk`（旧版直接覆盖）。
装完按 `BINDING.md` §2 把 `JOY_BTN13/14/15` 绑到减速板开 / 收、机轮刹车；
头瞄视角仍按 v1.2.0 的方式绑 `Absolute Camera View`，不受本次改动影响。

> **v1.3.1（2026-11-14，同次会话）**：把「减速板开/收 + 轮刹」这一行从中间杆位区移到右侧
> 「校零」与「解锁」之间（同属起降/整备类操作，放在一起更顺手）。`versionName 1.3.0→1.3.1`、
> `versionCode 4→5`；APK：`release/v1.3.1/DCS-Peripheral-Android-v1.3.1.apk`。功能与 DCS 绑键不变。

> **v1.3.2（2026-11-14，同次会话）**：武器控制从「武器↑/↓」两个按钮改成单个「武器切换」
> （`WEAPON_SWITCH = 3` → `JOY_BTN4` → `S8: Change Weapons`，脉冲）。JF-17 只有单向循环、没有上/下两条命令，
> 所以一个键就够，`JOY_BTN5` 释放。`versionName 1.3.1→1.3.2`、`versionCode 5→6`；
> APK：`release/v1.3.2/DCS-Peripheral-Android-v1.3.2.apk`。

> **v1.3.3（2026-11-14，同次会话）**：战斗页所有按钮改为瞬时触发，去掉 150/250ms 防误触延时
> （`GuardButton` 的 `guardMs` 全部置 0）。武器切换 / 锁定 / 干扰弹 / 机炮 / 武器投放按下即生效，
> 红框等视觉警示保留。`versionName 1.3.2→1.3.3`、`versionCode 6→7`；
> APK：`release/v1.3.3/DCS-Peripheral-Android-v1.3.3.apk`。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | **先读这个** |
| `docs/PANEL.md` | iPad 仪表盘：字段含义、三个硬限制 |
| `docs/YOKE.md` | 手机摇杆：页面、手感、配平、DCS 绑键 |
| `docs/BINDING.md` | vJoy 按钮/轴 ↔ 功能对照表 |
| `docs/DCS-DATA.md` | DCS 能读到什么、读不到什么（实测） |
| `docs/JF17-CONTROLS.md` | 68 个可远程操作的座舱开关 |
| `docs/JF17-MFD.md` | MFD 周边键语义（U1/D3/R8…） |
| `docs/LAYOUT.md` | 外设分工框架：什么该上手机 |

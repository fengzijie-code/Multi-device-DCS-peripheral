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

**发布时已知的限制**（不阻塞 v1.00）：发射键 250ms 长按门槛、7–9 号仍是预留位
（缺 ACM 格斗模式 / 目标解锁）→ 单次开火可行，不足以持续空战对抗；
机炮需先在 iPad 的 SMS 页选 GUN + FEED 充弹；视角松手回中且与发射键同手。
详见 [`docs/BINDING.md`](docs/BINDING.md) §9 与 `docs/TEST-REPORT.md` 第 8 节。

> `.gitignore` 默认忽略 `*.apk`；v1.00 这一个发布包已用 `git add -f` 随 tag
> 一起入库，方便回滚时直接取包。后续版本若仓库体积变大可改走外部附件。

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

# 版本历史

每个版本改了什么、**为什么改**，都在这里。README 只放「怎么用」，不放流水账。

| 版本 | 日期 | 一句话 |
|---|---|---|
| **v1.4.0** | 2026-11-19 | iPad 当杆：玻璃 HUD 四页 + 一键启动（**无新 APK**） |
| v1.3.0 ~ v1.3.7 | 2026-11-14 | 起降页加减速板/轮刹；战斗页连续 7 次微调（同次会话） |
| v1.2.0 | 2026-11-14 | 移除手机端视角轴，交给头瞄 |
| v1.1.0 | 2026-11-14 | 补上 iPad 端部署包，双端齐全 |
| v1.00 | 2026-11-13 | 第一个正式 release：三条链路全通（含视角） |

> 时间正序，最新在最下面。APK 按版本放在 `release/<tag>/`；
> `.gitignore` 忽略 `*.apk`，只有 v1.00 的包是 `git add -f` 强推进库的。

---

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

> **v1.3.4（2026-11-14，同次会话）**：战斗页重排 —— ① 干扰弹从中间挪到右上发射组最左（机炮左侧）；
> ② 新增 **TDC 雷达光标四向**（上 / 下 / 左 / 右，菱形排布在方框内，按钮按住即持续移动雷达光标），
> 占 `BTN5 / BTN8 / BTN9 / BTN10`（原预留位，不新增编号、不改 vJoy 按钮数）；③ 雷达锁定移到四向键左侧（组成「雷达簇」）。
> 四个方向绑到 JF-17 的 `TDC Slew Up/Down/Left/Right`（见 `BINDING.md` §2）。
> `versionName 1.3.3→1.3.4`、`versionCode 7→8`；APK：`release/v1.3.4/DCS-Peripheral-Android-v1.3.4.apk`。

> **v1.3.5（2026-11-14，同次会话）**：把右侧操作组整体放大以便盲操 —— 右列 220→250dp、发射行 78→94dp、
> 锁定 54→60dp、雷达簇 158→200dp、TDC 箭头 46→56dp（字号也相应加大）。布局不变，仅尺寸放大。
> `versionName 1.3.4→1.3.5`、`versionCode 8→9`；APK：`release/v1.3.5/DCS-Peripheral-Android-v1.3.5.apk`。

> **v1.3.6（2026-11-14，同次会话）**：修正「倾角过大」误判导致的断线 —— 原阈值约 55° 会在大过载机动
> （手机 tilt 到 90°+）时把人直接踢掉并自动上锁，用户反馈「拉过载时给我断线」。现把异常阈值提到 ±180°
> （只有物理上不可能的姿态才判异常），90°+ 满载输入正常处理、不再断线；阈值触发后的兜底行为（输出零、
> 持续 1.2s 才上锁、提示「倾角过大」）保持不变，但正常飞行（含极大过载）永远不会走到这一步。
> 改动只在 `YokeController.kt`（阈值 55°→180°，同步更新类注释）。`versionName 1.3.5→1.3.6`、
> `versionCode 9→10`；APK：`release/v1.3.6/DCS-Peripheral-Android-v1.3.6.apk`。

> **v1.3.7（2026-11-14，同次会话）**：修复战斗页右下角 TDC 「下箭头」被截断/遮挡。
> 根因：右侧整列（发射三键行 + 雷达 TDC 簇）纵向过高、被挤出屏底，把最底部的「↓」裁掉；
> 同时脚舵 `fillMaxWidth` 横跨整屏、右端压在「↓」底下。修法：① 脚舵缩短**水平长度**
> （`RudderBar` 由 `fillMaxWidth` 改为固定 `540.dp`、靠左放，约 6 成屏宽、仍是条像样的滑块而非残根）；
> ② 发射三键行 `94.dp→58.dp`、TDC 四向箭头 `56.dp→58.dp`（字号 `22→24sp`）、雷达簇内边距 `12→10dp`，
> 给「↓」腾出纵向空间；③ 脚舵高度保持 `34.dp` 不变。改动只在 `CombatScreen.kt`。
> `versionName 1.3.6→1.3.7`、`versionCode 10→11`；APK：`release/v1.3.7/DCS-Peripheral-Android-v1.3.7.apk`。

---

## v1.4.0 —— iPad 当杆、玻璃 HUD、一键启动（2026-11-19）

> **触发**：iPad 那条路要能真的飞。用户给了 4 张 F-18 的 iPad 画面，要求照"边缘那一圈
> 叠加 UI"的观感重做，并明确只说横屏（不做竖排）。随后依次修了脚舵位置、顶部安全区、
> 解锁键够不着、启动时一堆 Wi-Fi 噪音这些实飞才会暴露的问题。
>
> **这一版没有新 APK**：`android/` 自 `v1.3.7` 一个字节没动，Android 端继续用
> `release/v1.3.7/DCS-Peripheral-Android-v1.3.7.apk`（`versionName 1.3.7` / `versionCode 11`）。
> 变的是 PC 服务和 iPad 页面。

| 项 | 值 |
|---|---|
| Git tag | `v1.4.0` |
| Android | 未改动，仍 `1.3.7` / `11` |
| 说明 | [`release/v1.4.0/RELEASE.md`](release/v1.4.0/RELEASE.md) |
| 升级 | `git pull` 后双击 `tools\start-ipad.bat`；iPad 上刷新页面即可（不必重装、不必重装描述文件） |

**这一版包含**：

- **iPad 输入端 `/yoke` 重做**（`tools/yoke.html`，1400 行）——
  照 Pixel 端分四页：**仪表 / 起降 / 战斗 / 校准**；换页时杆盘**不挪位**（`#colL` 定宽、
  两套右列面板互相顶替），因为推着杆切页时杆心跳一下，杆量会甩。
- **美术换成"玻璃 HUD"**：不画面板 —— 没有卡片底色、没有边框盒子、没有实心顶栏，
  只有 1px 细描边、圆、小字距的浅色字。克制是有原因的：底图是 DCS 座舱，
  任何实心色块都会变成"网页控件"贴在上面。
- **手感内核**从 Pixel 端搬齐：默认上锁、按钮最短脉冲 120ms、死区/行程/expo 三参数、
  配平（force trim）、体感（陀螺仪）与校零、姿态异常兜底。
- **一键启动** `tools/start.py` + 两个 `.bat` 薄壳 —— 起服务前先查四件事
  （证书有效 / SAN 含当前 IP / 三个端口空闲 / 防火墙放行），因为它们失败时在 iPad 上
  表现完全一样；服务起来后印**真实在听**的那个 IP，并自检 `http 200 · https 200`。
- **修复**（都是实飞才暴露的）：
  - 证书有效期 3650 天 → **365 天**：iOS 上限 398 天，超了在握手层直接断开，
    Safari 只报"已丢失网络连接"，是最容易误判成网络问题的一个坑。
  - TLS 握手从事主线程的 `accept()` 里挪走：以前一条"连上但不发 ClientHello"的
    连接就能把整个 8443 堵死。
  - 8443 兼收明文 HTTP（地址栏只写 `ip:8443` 的那种请求），并补 `close_notify`。
  - 端口预检改按 `netstat` 的 LISTENING 判 —— Windows 的 `SO_REUSEADDR` 语义和 Unix
    相反，端口被占时加了它 `bind` 照样成功，试探性 `bind` 会给出假的"空闲"。
  - `mock` 的 `--target`、`beacon` 的 `--input-out` 都跟着端口参数走（以前改了端口
    就"两边日志都正常、杆却不动"）；USB 模式不再打印一整屏 Wi-Fi 地址。
- **JF-17 训练页**（`jf17-trainer/`）：座舱虚拟按键训练 + 冷启动流程。

---

## v1.4.1 —— 油门默认反转 + 显示层修正（2026-11-20）

| 项 | 值 |
|---|---|
| Git tag | 未打 tag（跟随 main） |
| Android | 未改动，仍 `1.3.7` / `11` |
| 升级 | `git pull` 后重启 `tools\start-ipad.bat`，iPad 上刷新页面 |

**改了什么、为什么**：实飞发现 iPad 端油门两件事都不对——

1. **默认该反转而没反转**：DCS 那边油门轴方向相反，iPad 这头得发 `1 − 手指位置`
   去补。`invT` 默认值从 `false` 改成 `true`（校准页开关仍可手动关）。
2. **反转不该碰显示层**（真正的 bug）：`setThr()` 以前把手指位置反转完再拿去画
   旋钮/油门条/百分比，于是反转一开，手往上推、屏上油门反而往下走。
   现在显示永远跟着手走（上推 = 加油门），反转只作用在发往 beacon 的 `st.t` 上。
   中途切换反转开关时发送值取补（原逻辑保留），显示不动。

`tools/check-yoke.py` 同步：油门 1/4 处断言从 0.75 改成 0.25（默认反转），
并新增验收「屏上油门旋钮停在手指位置（显示不反转）」——这条就是本次翻车的验收。

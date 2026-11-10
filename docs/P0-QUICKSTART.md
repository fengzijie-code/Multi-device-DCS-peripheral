# P0 快速上手

目标：**今天就能回答「我这台手机的校园网到底能不能连上 PC」**，不用装 DCS，不用 Android Studio。

全部依赖只有：Python 3.11+。

---

## 步骤 1 · 摸清本机网络

```bash
python tools/netprobe.py
```

输出里重点看四行：

| 要看什么 | 为什么 |
|---|---|
| **物理网卡在哪个网段** | 例如 `10.180.0.0/15`。手机必须在这个网段里，① 才有意义 |
| **有没有公网 IPv6** | 有的话 ② 这一档有希望，但校园网常封入站 |
| **有没有 Tailscale 地址** | 有 ③ 这一档，基本就不用折腾了 |
| **mDNS 是否可用** | 决定能不能自动发现 PC，不可用就只能手输 IP |

同时会写出 `docs/NETWORK-PROBE.md`。

---

## 步骤 2 · 起信标，用手机打开

```bash
python tools/beacon.py --port 8080
```

控制台会打印几个候选地址，形如：

```
http://10.180.211.30:8080/
http://[2403:d400:1000:12:...]:8080/
```

**逐个在手机浏览器里试。** 能打开 = 这条路径通；打开后看 RTT 数字跳动。

### 打不开？按这个顺序排查

1. **防火墙授权框**。第一次监听时 Windows 会弹框，必须允许，并且勾「专用网络」。
   如果当时点了取消，去「Windows 安全中心 → 防火墙 → 允许应用通过防火墙」里补上。
2. **网络配置文件是 Public**。Public 配置文件默认拒绝入站。
   ```powershell
   Get-NetConnectionProfile          # 看 NetworkCategory
   ```
   若是 `Public`，需要改成 `Private`（管理员权限，自己执行）：
   ```powershell
   Set-NetConnectionProfile -InterfaceAlias "WLAN" -NetworkCategory Private
   ```
3. **手机不在同一网段**。对比 netprobe 输出的网段与手机 WiFi 详情里的 IP。
4. **校园网开了客户端隔离**。这是最常见的死因 —— 两个设备在同一网段也互相不可达。
   此时步骤 3 是你唯一的出路。

---

## 步骤 3 · 校园网隔离时的三条出路

按优先级试：

| 顺位 | 做法 | 预期 |
|---|---|---|
| ① | 装 Tailscale，PC 和手机登录同一账号 | 信标地址换成 `100.x.x.x` 再试 |
| ② | **手机开热点，PC 连热点** | 最稳，5 ms 级别。PC 保持校园网为默认路由即可 |
| ③ | 租台便宜 VPS 做中继 | 最后手段，50–150 ms |

关于 ② 的细节：PC 同时连校园网和手机热点时，给校园网网卡设更低的接口跃点数（默认走校园网），
只让外设流量走热点。这样 PC 照常能上网、能打多人，而外设走一条干净的局域网。

---

## 步骤 4 · 验证遥测链路（不需要 DCS）

开两个终端：

```bash
# 终端 A：先跑 mock，看它自己发得对不对
python tools/mock_export.py --profile maneuver --duration 10

# 终端 B：随手抓一下，确认 60Hz 和字段都对
python -c "
import socket,json
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('127.0.0.1',5010)); s.settimeout(2)
for _ in range(3):
    d,_=s.recvfrom(4096); print(json.loads(d))
"
```

注意：终端 A 会一直占着 5010，所以 **先跑 B 再跑 A**，或者把 B 的 bind 换个端口。

---

## 步骤 5 · 接入真实 DCS

1. 把 `dcs/Export.lua` 复制到：
   ```
   %USERPROFILE%\Saved Games\DCS\Scripts\Export.lua
   ```
   （`DCS.openbeta` 同理）

   **如果该文件已存在**（装了 DCS-BIOS / DCS-ExportScripts），不要覆盖，
   把本文件里 `LuaExportStart` / `LuaExportAfterNextFrame` / `LuaExportStop`
   三段并进去。

2. 启动 DCS 进一个单机任务，然后看日志：
   ```
   %USERPROFILE%\Saved Games\DCS\Logs\dcs.log
   ```
   搜 `DCSMultiPeriph`，应该看到：
   ```
   已启动：发往 127.0.0.1:5010，目标 60 Hz。LuaSocket OK。
   ```

3. 若报 `无法加载 LuaSocket`：把 LuaSocket 的 `socket.dll`、`mime.dll`
   和 `lua/socket/` 目录放进 `Saved Games\DCS\Scripts\`。

---

## 步骤 6 · 构建并安装 Android 客户端

工程在 `android/`，已经带了 Gradle wrapper，不依赖 Studio 也能构建。

### 6.1 命令行构建

```bash
cd android

# 关键：系统里的 JAVA_HOME 指向一个并不存在的 JDK 1.8，必须覆盖成 Studio 自带的 JBR
export JAVA_HOME="D:/Android Studio/jbr"
export PATH="$JAVA_HOME/bin:$PATH"

./gradlew :app:assembleDebug
```

产物：`android/app/build/outputs/apk/debug/app-debug.apk`（约 12 MB）

### 6.2 装到 Pixel

1. 手机开「开发者选项 → USB 调试」，用数据线连 PC
2. 确认设备可见：
   ```bash
   "$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" devices
   ```
3. 安装并启动：
   ```bash
   "$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" install -r android/app/build/outputs/apk/debug/app-debug.apk
   "$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" shell am start -n com.fengzijie.dcsperipheral/.MainActivity
   ```

### 6.3 让它显示数据

三个终端：

```bash
# A. 起信标 + 遥测汇聚
python tools/beacon.py --port 8080

# B. 喂假数据（或换成真 DCS）
python tools/mock_export.py --profile maneuver

# C. 浏览器先验一下接口
curl -s http://127.0.0.1:8080/state
```

然后在 App 里点右上角「设置」，填：

```
http://<信标启动时打印的 IP>:8080
```

连上后，姿态仪会跟着 mock 的 `maneuver` 剖面滚转、俯仰，四个数字实时跳动。

### 6.4 日常启动：双击一个脚本

```bash
tools/start-usb.bat
```

它会依次：起桥接（:8080）→ 起 mock 遥测（60 Hz）→ 建立 `adb reverse` → 拉起 App。
弹两个黑窗口，关掉即停。

### 6.5 为什么默认走 USB

实测过四条路，只有 USB 可用（详见 `docs/NETWORK-FINDINGS.md`）：

| 路径 | 实测延迟 | 结论 |
|---|---|---|
| **USB + adb reverse** | **2–4 ms** | ✅ 默认 |
| 校园网直连 / IPv6 | 不可达 | ❌ 客户端隔离 |
| PC 移动热点 | 100–900 ms | ❌ 延迟不可接受 |
| 便携路由器 / Tailscale | 未测 | 留待 P2 |

USB 的额外好处：**手机同时被供电**，不用担心电池；也不受任何无线环境干扰。

> 注意：`adb reverse` 需要开发者模式 + USB 调试授权，适合开发期。
> 将来做给普通用户时，应该换成 **USB 网络共享（RNDIS）** 或 **AOA 配件模式**，
> 这两种都不需要开开发者选项。

### 6.6 这套工具链的三个坑（都已在工程里处理）

| 坑 | 现象 | 处理 |
|---|---|---|
| AGP 9 内置 Kotlin | 加 `org.jetbrains.kotlin.android` 直接构建失败 | 已移除，只保留 `com.android.application` |
| KGP 版本落后 | Compose 库报 `incompatible version of Kotlin` | 顶层 `buildscript` 把 KGP 抬到 2.4.21，与 Compose 插件同版本 |
| 系统 JAVA_HOME 失效 | `ERROR: JAVA_HOME is set to an invalid directory` | 构建前覆盖为 `D:/Android Studio/jbr` |

---

## 步骤 7 · 跑测试

```bash
python -m pip install lupa          # 只用来跑 Export.lua 的功能测试
python tests/test_export_lua.py
```

这个测试用嵌入式 Lua 加载**真实的** `Export.lua`，注入假的 `LoGet*` 和 socket，
校验报文格式、字段顺序、节流、NaN 清洗、无 socket 时的降级。当前 20 条全绿。

---

## 当前进度

| 项 | 状态 |
|---|---|
| `tools/netprobe.py` | ✅ 可用，已在本机验证 |
| `tools/beacon.py` | ✅ 可用；`/state` 遥测汇聚已验证（60.0 Hz，stale 判定正确） |
| `tools/mock_export.py` | ✅ 可用，60.3 Hz / 11 字段已验证 |
| `dcs/Export.lua` | ✅ 语法通过 + 20 条功能测试通过 |
| `android/` | ✅ `assembleDebug` 成功，产出 12 MB APK；**尚未在真机运行过** |
| Rust 桥接服务 | ⬜ 下一步（P1），替换掉 beacon 里的 Python 版 `/state` |
| 加密与配对 | ⬜ P2 |

---

## 已知限制

- **信标是明文 HTTP**。它在 P0 的唯一职责是回答「通不通」+ 喂数据，不承担加密。
  P1 换成 HTTPS + 自签名证书，P2 加双向证书与二维码配对。
- **信标不做鉴权**。局域网内任何人都能打开。只在你自己的网络里临时开。
- **App 用 HTTP 轮询（10 Hz）**，不是最终架构。轮询在 P0 只为了少踩依赖的坑；
  P1 换成 QUIC 长连接后，指令通道才能做到低延迟。
- **mock 与真机的字段一致性靠人肉同步**。等 P1 把 `.proto` 定下来，两者都从同一份
  schema 生成，就不会漂了。
- **APK 还没上过真机**。构建通过 ≠ 运行正确，第一次装上去大概率还要修一两处布局。

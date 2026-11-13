# 上 DCS-BIOS 的代价评估

> 2026-11-13｜针对「雷达模式/返回、塔康输入、航路点、无线电频率、武器选择、状态检测准确性」
> 查证来源：DCS-Skunkworks/dcs-bios `main` 分支 README / BIOS.lua / BIOSConfig.lua /
> `lib/modules/aircraft_modules/JF-17.lua` / developerguide.adoc（2026-11-13 在线核对）

---

## 0. 一句话结论

**不建议为了这几个功能上 DCS-BIOS。** JF-17 的官方 BIOS 模块**没有导出雷达模式、塔康频道/程序、
航路点、武器挂点、MFCD 页面文本**——上了也拿不到。真正卡住我们的不是「没用 BIOS」，
而是 `Export.lua::mfd_tokens` 把屏幕上的动态数字丢了；改几行 Lua 的收益比引入整套 BIOS 高一个量级。

DCS-BIOS 唯一能实质提升的是：**293 个控件 + 116 个指示灯的真实状态回读**，
让我们从「看 `dbg` 回执」升级到「看控件真的动了」。这是另一个目标，值得单独评估。

---

## 1. 事实核查（先把传闻纠正）

| 项 | 查证结果 | 对项目的影响 |
|---|---|---|
| 项目是否活跃 | ✅ 活跃。Nightly 2026-02-01、v0.8.4；原 `dcs-bios` 已停更，现在是 **DCS-Skunkworks fork** | `docs/ROADMAP.md` 里「DCS-BIOS 项目停滞」这条风险**已过时** |
| JF-17 支持 | ✅ 官方模块存在（`WarLord` / `cdpkobra` 贡献），`BIOS.lua` 里显式 `require(...aircraft_modules.JF-17)` | 不用自己写机型适配，省掉最大的一块 |
| 模块导出规模 | 约 **444 项**：~293 物理控件、116 指示灯、6 字符串、3 整数、~10 仪表浮点、~14 外部模型状态、99 个 MFCD 边框按键 | 控件层很全，**显示/数据层很薄** |
| 安装方式 | 复制 `DCS-BIOS/` 到 `Saved Games/DCS/Scripts/`；**已有 `Export.lua` 时只需在末尾加一行** `dofile(lfs.writedir() .. [[Scripts\DCS-BIOS\BIOS.lua]])` | 不用替换我们现有的 `Export.lua` |
| 钩子冲突 | ✅ `BIOS.lua` 用 `PrevExport` 保存并 `call_function_safe` **链式调用**原有的 `LuaExportStart/Stop/BeforeNextFrame/AfterNextFrame` | 两条导出链可以共存，这是省事的关键 |
| 导出协议 | UDP 组播 `239.255.50.10:5010`（回环接口），16 位地址空间二进制增量流（address/mask/shift），`export_rate=30`（范围 1–30） | 不是 JSON，要写解析器 |
| 输入协议 | UDP/TCP `7778`，纯文本 `"IDENTIFIER ARG\n"`；另有 `tcp_config = {address="*", port=7778}` | 比我们现在的 `dcs_cmd.txt` 文件通道可靠 |
| 配置 | `BIOSConfig.lua` 可改 `send_address/send_port/receive_address/receive_port`、`export_rate`、`dev_mode` | 端口可挪开 |
| 许可 | GPL-3.0 | 本机自用无影响；分发要注意 |

---

## 2. 关键发现：上了 BIOS，你问的 6 类里 5 类还是拿不到

逐个查 `JF-17.lua` 的导出标识符：

| 你要的 | BIOS 里有没有 | 证据 |
|---|---|---|
| 雷达模式 RWS/TWS/VS/STBY | ❌ **没有** | `RADAR`/`RWS`/`TWS`/`STBY` 精确命中 0；只有 `AAP_RDR_BTN`（按钮）和 `AAP_BTN_L_RDR`（指示灯） |
| 塔康频道 / TCN 程序 | ❌ **没有** | `TACAN`=0；`TCN` 只命中 `TCN_ILS_VOL_KNB`（音量旋钮） |
| 航路点 / WPT 数值 | ❌ **没有** | `WPT`=0；只能靠通用 `UFCP_LINE_*` 文本间接看 |
| 无线电频率 | ⚠️ **部分** | `COMM1`/`COMM2` 是 `defineReadWriteRadio`（可读写电台控件），`RADIO_LINE_1/2` 是字符串；**没有 `COMM1_FREQ` / `COMM1_CHANNEL` 命名导出** |
| 武器挂点 / CurrentStation / SMS | ❌ **没有** | `SMS`/`STATION`/`CurrentStation` 全部 0；我们自己的 `sys.st/wn/wc/wl` 反而已经有 |
| MFCD 页面 / 显示文本 | ❌ **没有** | 99 个 `MFCD_L/C/R_*` 全是**边框按键输入**，没有 `MFCD_PAGE`/`MFCD_TEXT`/显示字符串 |
| UFCP 四窗文本 | ✅ 有 `UFCP_LINE_1~4` | **和我们已经回传的 `sys.ufcp` 等价**，重复建设 |

> 换句话说：我们现在的 `sys.ufcp`（四窗文本）+ `sys.mfd`（元素名/全大写词）
> 在「显示层」并不比 BIOS 少，甚至多一项 MFD 屏幕指纹。
> BIOS 强的是**控件与灯的状态**，不是**屏幕上的数据**。

要真正拿到雷达模式/塔康频道/航路点数值，只有两条路：
1. 自己给 JF-17 **补写 DCS-BIOS 模块定义**（从 `clickabledata.lua` / `command_defs.lua` / 指示器 dump 反推地址）——几十人日，且随 DCS/BIOS 版本漂移；
2. 直接读原始 `list_indication` dump —— 我们**已经在调这个接口**，只是把数字过滤掉了。

---

## 3. 硬冲突清单（真要上，必须先处理）

| # | 冲突 | 说明 | 处理 |
|---|---|---|---|
| 1 | **UDP 5010** | BIOS 默认发往组播 `239.255.50.10:5010`；我们 `Export.lua` 往 `127.0.0.1:5010` 发 JSON、beacon **绑定** `127.0.0.1:5010` 收 | 默认目标地址不同、理论可共存，但同端口同回环接口很脆弱；一旦有人把 BIOSConfig 改成单播 `127.0.0.1:5010`，beacon 会把二进制流当 JSON → `bad` 暴涨、遥测被污染。**必须挪开一边** |
| 2 | `Export.lua` 唯一文件 | 两边都要它 | 末尾加 `dofile` 一行即可（钩子有链式调用）。但**改完必须重启 DCS 任务** |
| 3 | 帧开销 | `export_rate=30`、每帧遍历 444 项；`dev_mode=true` 任务启动时会写 json/header 地址表 | 关 `dev_mode`（但那样就拿不到地址表了）、或接受；文档明确说 TCP 连接会阻塞模拟，优先 UDP |
| 4 | 版本漂移 | 地址表随 BIOS 版本变；JF-17 模块本身也修过（release 里有 `JF-17 null replaced with nil`） | 每次升级重新生成映射 + 回归，需锁定版本号 |
| 5 | 多人服务器 | 部分服务器禁用导出脚本 | 与现有 `Export.lua` 同样的降级路径，能力探测要覆盖两条链 |
| 6 | DCS 重装/升级 | `Saved Games/DCS/Scripts` 可能被覆盖 | 现有 `T-E2E-006` 自检要扩展到 BIOS 目录 |

**端口最小改法**（推荐改我们这边，不动 BIOS 默认值）：
`dcs/Export.lua` 的 `CFG.port` 与 `tools/beacon.py` 的 `--udp-in`（`run-all.py` 里也要同步）从 `5010` 改成 `5012`；
三处常量，约 30 分钟，回归一次 82 项即可。

---

## 4. 代价拆解（人日，按「只做只读」最小方案）

| 阶段 | 做什么 | 人日 |
|---|---|---|
| 0 · 可行性验证 | 下载 release → 装 `DCS-BIOS/` → 在 `Export.lua` 末尾加 dofile → 端口隔离 → 抓一帧确认钩子链没断、JF-17 模块加载、我们 60Hz 遥测仍在 | 1 |
| 1 · 导出解析 | Python 解析 16 位地址空间增量流（address/mask/shift）+ 用 `dev_mode` 生成的 JSON 控件表做映射 → 合并进 `/state`（新字段，比如 `bios`） | 2–3 |
| 2 · 输入侧（可选） | 把 `/cmd` 从 `dcs_cmd.txt` 换成 UDP 7778 文本命令，解决单槽丢命令；保留文件通道做兜底 | 1–2 |
| 3 · 回归 | 重跑 82 项离线 + 11 项真机 + 功能层 14 项；补 BIOS 降级用例（BIOS 没起 / 地址表不匹配 / 多人服禁导出） | 1–2 |
| **合计（只读）** | | **5–8 人日** |
| 完整 P2（含 ControlRef / 配对 / 看门狗 / Profile） | `docs/ROADMAP.md` 原估算 | **12–16 人日** |

外加持续成本：每次 DCS-BIOS 升级要重新生成地址表并回归；每次 DCS 大版本升级要重新部署 Scripts。

---

## 5. 收益对照（这才是决策依据）

| 目标 | 上 BIOS 后的效果 |
|---|---|
| 雷达模式闭环验证 | ❌ 仍然不行 |
| 塔康频道数值验证 | ❌ 仍然不行 |
| 航路点数值验证 | ❌ 仍然不行（只能多 `RADIO_LINE_1/2`） |
| 无线电频率验证 | ⚠️ 略好：多两条电台显示字符串，仍不是 MHz 频率 |
| 武器选择验证 | ❌ 无变化（我们已经有 `CurrentStation`） |
| **按键→真实控件状态** | ✅ **质变**：从 `dbg=…:D`（方法调用了）变成「这个开关/灯的真实状态」，116 个灯 + 293 个控件 |
| 命令通道可靠性 | ✅ 可以从文件单槽换成 UDP 7778，不再丢命令 |
| 状态检测准确性（MFD 页面） | ❌ 无帮助，BIOS 不导出页面；41 页无指纹的问题照旧 |

---

## 6. 三条路线

| 路线 | 投入 | 能解锁 | 建议 |
|---|---|---|---|
| **A · 改自己的导出（推荐）** | **0.5–1 人日** | 塔康/航路点/频率的**屏幕数字**、MFD 页面原始文本、更准的页面识别 | ✅ 先做这个 |
| B · 最小 BIOS 只读 | 5–8 人日 | 控件/灯真实状态、可靠的输入通道 | 只有当目标变成「座舱硬件回读」时才做 |
| C · 完整 P2（ROADMAP 那套） | 12–16 人日 | ControlRef / 配对 / 多机型 Profile | 当前单人 JF-17 场景不划算 |

### 路线 A 具体做什么（最小改动，收益最大）

1. `dcs/Export.lua::mfd_tokens()` 现在只收 `^[a-z][a-z0-9_]*$` 与 `^%u[%u%d]+$`，
   **把短数字串也收进来**（`TCN01`、`001 001`、`60`、`4BR` 这类），`sys.mfd` 立刻带上塔康/频率/航路点数字。
2. 新增一个 `sys.mfd_raw`：`list_indication(8/9/10)` 的原始文本按 1Hz 回传、限长（比如每屏 2KB），
   测试和面板都能看到完整屏幕文字，不再靠猜元素名。
3. `sys.ufcp` 已有四窗文本，补一个语义拆分（`wpt` / `com1` / `com2` / `ap`）便于断言。
4. 用这些新字段重写 `tests/live_features_test.py` 里标 `LIMIT` 的 4 项，从「测不了」升级成 `VERIFY`。
5. **代价**：改 `Export.lua` → 重启一次 DCS 任务；`panel.html` 刷新即可；回归 82 + 11 + 14 项。

> 这条路不需要引入第三方依赖、不需要处理组播端口、不需要写二进制解析器，
> 而且修的是我们自己的真实缺陷（`mfd_tokens` 丢数字），不是补外部能力。

---

## 7. 如果仍决定上 BIOS：阶段 0 检查清单

```
[ ] 从 DCS-Skunkworks/dcs-bios releases 取 v0.8.4（记录 commit / 版本号）
[ ] 备份 Saved Games/DCS/Scripts/Export.lua
[ ] 复制 DCS-BIOS/ 到 Scripts/，在现有 Export.lua 末尾加一行 dofile
[ ] 把我们的遥测端口从 5010 挪到 5012（Export.lua CFG.port + run-all.py --udp-in）
[ ] 重启 DCS 任务，确认 /state 仍是 60Hz、has_data=true（钩子链没被覆盖）
[ ] 确认 BIOS 组播 5010 有数据、7778 能收文本命令
[ ] dev_mode=true 抓到 JF-17 地址表 JSON，确认 UFCP_LINE_1~4 / RADIO_LINE_1~2 的地址
[ ] 逐一核对：雷达模式/TCN/WPT/STATION 是否真的没有导出（本评估的结论需要实测复核）
[ ] 记录帧率与 CPU 开销基线（开/关 BIOS 各一次）
```

**回退**：删掉 `Export.lua` 末尾那行 dofile、还原端口常量、移除 `DCS-BIOS/` 目录，重启任务。

---

## 8. 结论

- 上 BIOS 的**直接代价**是 5–8 人日（只读）/ 12–16 人日（完整 P2），
  外加端口冲突、版本漂移、每次重启任务的持续成本。
- 但**对你当前问的 6 类功能，它基本不解决问题**：JF-17 的 BIOS 模块压根没导出那些数据。
- 真正卡住的是我们自己的 `mfd_tokens` 丢了屏幕数字，**0.5–1 人日就能修**，
  而且不需要引入 GPL 依赖、不需要组播、不需要二进制解析器。
- 建议：先做路线 A；等目标升级到「座舱控件/指示灯真实状态回读」时，再按阶段 0 重新评估 BIOS。

# 真 DCS 虚拟输入 → 状态输出对应测试

> 执行时间 2026-11-13 14:47:21 ｜ 目标 `http://127.0.0.1:8080` ｜ 机型 `JF-17`
> 脚本：`tests/live_dcs_test.py` ｜ 明细：`.tmp/live-dcs-result.json`

## 环境实况（测试开始时读到的状态量）

- `has_data=True`、`stats.hz=59.9`、`bad=0`、`age=5ms`
- `sys.ac=JF-17`、`sys.t=133.34`、`sys.dbg=47:3295:D`、`acn=20`、`bp=7:793,793,769,793,807,774,741`
- `sys.ufcp=FP-A 01|CAS MAN||001 001`

## 逐项对应

| ID | 虚拟输入 | 期望的状态输出 | 实际读到 | 判定 |
|---|---|---|---|---|
| T-LIVE-001 | `POST /cmd {dev:0,cmd:0,val:1} 读座舱参数 1` | HTTP 200 且 sys.dbg 变成 arg1=<数值> | HTTP 200 {"ok":1} → dbg=arg1=0 (sys.t=136.38) | ✅ |
| T-LIVE-002 | `POST /cmd {dev:0,cmd:0,val:3007} 换参数号` | sys.dbg 精确反映参数号 arg3007=<数值> | HTTP 200 → dbg=arg3007=0 | ✅ |
| T-LIVE-003 | `POST /cmd {dev:0,cmd:1} 设备扫描` | sys.dbg 以 devs= 开头且列出有 performClickableAction 的设备 | HTTP 200 → dbg=devs=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,37,38,39,…（133 字符） | ✅ |
| T-LIVE-004 | `POST /cmd {dev:0,cmd:3,val:734} 参数快照` | sys.dbg = A734\| 后跟 40 个数值，起始号随输入变 | HTTP 200 → A734\|0.00,0.00,0.00,0.00,0.00,0.00,0.00,1.00,0.00,0.00,0.00,0.00,0.00,0.00,0.00,… 共 40 个值 | ✅ |
| T-LIVE-005 | `POST /cmd {dev:99,cmd:3007,val:1} 不存在的设备` | sys.dbg = 99:3007:N（:N = GetDevice 返回空），飞机状态不变 | HTTP 200 → dbg=99:3007:N | ✅ |
| T-LIVE-006 | `只读：检查慢变量里的起落架进度 gr / 升降舵偏度 cs_e` | 新部署的 Export.lua 应给出数值（gear.nose.rod / elevator.left） | gr=0.0  cs_e=-0.0397  cs_a=0.0  cs_r=-0.0 | ✅ |
| T-LIVE-007 | `只读 GET /input（不写，避免动 vJoy）` | 能读到 axes/buttons/seq/forwarding/vjoy 结构 | axes={'x': 0.0, 'y': 0.0, 'r': 0.0, 'vx': 0.0, 'vy': 0.0, 't': None} forwarding=True vjoy={'alive': True, 'ok': True, 'age_ms': 715, 'msg': 'Device 1 vJoy'} | ✅ |
| T-LIVE-008 | `中屏 D3 (dev47 cmd3295) 回主菜单` | sys.mfd 的 C= 段含 MENU/RDR/INS/TACAN/…/CHKLS 主菜单标签 | C= 段 19 token，含 CHKLS=True, BIT=True | ✅ |
| T-LIVE-009 | `中屏 U1 (cmd3271) 从主菜单进雷达页` | sys.mfd 的 C= 段不再含 CHKLS/BIT，且 sys.bp 序号 +1（座舱按键被扫到） | CHKLS=False  bp 8→9  C 段前 16 个=['BCN', 'CNTL', 'GMTI', 'IFF', 'LOWER_BASE', 'MAP', 'RDY', 'RTN', 'RWS', 'SEA1', 'SEA2', 'TA', 'TWS', 'UPPER_BASE', 'VS', 'WA'] | ✅ |
| T-LIVE-010 | `中屏 D3 再次按下（cmd3295）` | sys.mfd 的 C= 段重新出现 CHKLS（回到主菜单），输入可逆 | CHKLS=True  bp=10:793,769,793,793,793,769,793,807 | ✅ |
| T-LIVE-011 | `UFCP PFL/1 (dev46 cmd3202)` | sys.dbg=46:3202:D 且 sys.acn 递增（回执闭环） | dbg=46:3202:D  acn 32→36  ufcp=FP-A 01\|CAS MAN\|\|001 001 | ✅ |

**汇总：11/11 通过，0 未达预期。**

## 版本自检（决定 T-LIVE-006 会不会失败）

| 组件 | 本轮判定 | 依据 |
|---|---|---|
| `Export.lua`（DCS 内存中） | 新版 ✅ | `sys.gr=0.0`、`sys.cs_e=-0.0379`；旧版这两个字段恒为 null |
| `Export.lua`（磁盘） | 与仓库一致（新版已部署） | 与 `dcs/Export.lua` 逐字节比对 |
| `beacon.py`（8080 进程） | 新版（HTTP 400 拒绝，不写命令文件） | `POST /cmd val=NaN` 的响应 |

> DCS 只在**任务启动时**加载 Export.lua；桥接进程也要重启才会加载新的 beacon.py。磁盘文件与内存版本可能不一致，两个都要查。

## 真机结构证据（dev=0,cmd=7 probe 通道只读取得）

```
gear.nose type = table
gear.nose.rod = 0
cs.elevator type = table
cs.elevator.left  = 0.0030272782314569
cs.elevator.right = 0.0030187647789717
gear.value = 0
```

`gear.nose.rod` 是三级嵌套、`controlsurfaces.elevator` 是 `{left,right}` 表。旧版 `deepget()` 只下钻两层，取回来的是 table，`numo()` 只能发 `null`（BUG-04）；新版 `deepget3()` / `surface()` 正是按这个形态写的。probe 用完已恢复原文件、删除诊断输出。

## 轮次记录

| 轮次 | 结果 | 说明 |
|---|---|---|
| 14:39 第一轮（重启前） | 10/11 | DCS 内存里是旧版 Export.lua、8080 是修改前的 beacon.py；`sys.gr/cs_*` 全 null |
| 14:45 第二轮（重启后） | 11/11 | 新版 Export.lua + 新版 beacon.py 全部生效；`gr=0.0`、`cs_e≈0.0072`、NaN 请求返回 400 |

## 补充观察

- 按中屏 U1 后 C= 段落到雷达模式菜单（`RWS/TWS/VS/MAP/GMTI/SEA1/SEA2/BCN/WA/TA`），与 `docs/JF17-MFD.md` 第八节一致；`sys.bp` 序号跟随按键递增。
- 按 D3 后 `CHKLS` 回来，页面可逆，输入没有卡住；UFCP 键回执 `:D` 且 `acn` 递增。

## 结论 / 下一步

- ✅ 新版 `Export.lua`、新版 `beacon.py`、真机三条链路全部验证通过，无需额外重启。
- 重复验证：`python tests/live_dcs_test.py --probe-version`。

## 安全约定

只发 `dev=0` 只读探针与 `dev=47/46` 的 MFD/UFCP 页面键（可逆）；不发起落架、襟翼、减速伞、主军械等改变飞行构型的命令；不写 `/input`（避免推动 vJoy 轴）。结束时用中屏 D3 回主菜单。

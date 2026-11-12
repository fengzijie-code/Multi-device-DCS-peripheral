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

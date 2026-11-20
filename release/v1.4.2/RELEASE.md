# v1.4.2 —— 无线为主：captive 显式开启 + 网络恢复工具

**日期**：2026-11-20
**Git tag**：`v1.4.2`
**Android**：**未改动**，仍是 `versionName 1.3.7` / `versionCode 11`
→ 继续用 [`release/v1.3.7/DCS-Peripheral-Android-v1.3.7.apk`](../v1.3.7/DCS-Peripheral-Android-v1.3.7.apk)

> 定位一句话：**可有线，但主要是无线**。有线直连能力原样保留（v1.4.1 那套
> 全在），但不再让每个无线用户的服务栈默认绑着 80/TCP + 53/UDP。

---

## 装 / 升级

```
git pull
tools\start-ipad.bat          # 无线：用法零变化，直接飞
tools\start-ipad.bat --captive   # 网线直连：显式开启探测应答器
```

iPad 上刷新页面即可，不用重装、不用重装描述文件。

---

## 这一版有什么

### 1. captive 探测应答器改为显式开启（`--captive`）

v1.4.1 里 `start-ipad.bat` 每次启动都自动带 `captive.py`（iOS 联网探测应答器，
常驻占用 80/TCP + 53/UDP）——那是「有线优先」的默认。实飞结论是有线延迟
满足不了需求、无线才是主路径，所以 v1.4.2 反转默认：

- `start.py` / `run-all.py`：`--no-captive` → `--captive`，**默认不启动**；
- 纯无线的服务栈从此不碰 80/53；
- 要走网线直连，`tools\start-ipad.bat --captive`（其余配置照 v1.4.1）。

### 2. 新增 `tools/restore-network.bat`：一键撤掉有线对电脑的改动

试过有线直连想回无线的机器，双击（自提权）一次就干净：

- 防火墙规则「DCS Peripheral Bridge」恢复为 **TCP 8080,8443**
  （删掉 captive 用的 80/TCP + 53/UDP 放行）；
- 撤掉 v1.4.1 固定的 `192.168.77.1/24`，有线网卡恢复 DHCP
  （无 DHCP 时自动回到 169.254.x.x 自分配，和以前一样）。

### 3. 有线直连能力原样保留

`tools/captive.py`、`tools/set-static-ip.bat`、文档章节全都在——
完整方案见 [`release/v1.4.1/RELEASE.md`](../v1.4.1/RELEASE.md)。

---

## 验收变化

- 无新增验收；v1.4.1 的油门/体感/触摸语义断言原样保留。
- 行为差异仅一处：`start-ipad.bat` 默认不再启动 captive 子进程。

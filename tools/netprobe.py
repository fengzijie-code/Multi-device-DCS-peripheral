#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netprobe.py — 多端 DCS 外设 · P0 网络探测

回答一个问题：在你现在这个网络里，手机能用哪条路连到这台 PC？

对应 ROADMAP 的四级降级阶梯：
    ① 同网段直连   ② 公网 IPv6   ③ Tailscale 打洞   ④ 中继   兜底: 手机热点

用法：
    python tools/netprobe.py                 # 探测 + 写报告到 docs/NETWORK-PROBE.md
    python tools/netprobe.py --json          # 输出 JSON（给 CI / 桥接服务消费）
    python tools/netprobe.py --peer 192.168.1.7:8080   # 额外测某个对端是否可达
    python tools/netprobe.py --no-report     # 只打印，不写文件

依赖：无。纯标准库，Windows / Linux / WSL 通用。
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import platform
import re
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 输出编码

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- 常量

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353
CGNAT = ipaddress.ip_network("100.64.0.0/10")      # Tailscale 用的网段
PROBE_PORTS_TCP = [8080, 8443, 5010]
PROBE_PORTS_UDP = [5010, 7778]

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)


def _c(text: str, color: str) -> str:
    """Windows 老终端可能不支持 ANSI，检测失败就返回原文。"""
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        if not os.environ.get("ANSICON") and not os.environ.get("TERM"):
            return text
    return f"{color}{text}{RESET}"


def ok(t): return _c("✓ " + t, GREEN)
def warn(t): return _c("! " + t, YELLOW)
def bad(t): return _c("✗ " + t, RED)


# ---------------------------------------------------------------- 基础工具

def sh(cmd: list[str], timeout: float = 4.0) -> str:
    """跑个外部命令，失败返回空串，绝不抛异常。

    注意：不能强制 utf-8。中文版 Windows 的 ipconfig / netsh 输出是 GBK，
    按 utf-8 硬解会把「适配器」变成乱码，后面所有基于适配器名的解析都会失效。
    这里按编码链逐个试，最后兜底 latin-1（永不失败）。
    """
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        raw = p.stdout or b""
    except Exception:
        return ""

    for enc in ("utf-8", "gbk", "cp936", "big5", "shift_jis"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", "replace")


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


# ---------------------------------------------------------------- 本机地址

def primary_ip() -> str | None:
    """拿到主出口 IP。

    经典技巧：对 UDP socket 做 connect（不会真的发包），内核会按路由表选源地址，
    然后 getsockname 就能读到。跨平台、无依赖、瞬时。
    """
    for target in ("8.8.8.8", 80), ("1.1.1.1", 443):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(target)
            return s.getsockname()[0]
        except Exception:
            continue
        finally:
            if s:
                s.close()
    return None


def _windows_gateway_and_ip() -> tuple[str | None, str | None]:
    """从 `route print -4` 解析默认网关与本地 IP。

    用 route 而不是 ipconfig，是因为 route 的输出格式与系统语言无关：
        0.0.0.0          0.0.0.0      192.168.1.1     192.168.1.55     25
    """
    out = sh(["route", "print", "-4"])
    for line in out.splitlines():
        m = re.match(
            r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)",
            line,
        )
        if m:
            return m.group(1), m.group(2)
    return None, None


def _posix_gateway() -> str | None:
    out = sh(["ip", "route", "show", "default"])
    m = re.search(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


# 这些关键字出现在适配器名里，基本可以断定不是手机能直连的那块网卡
VIRTUAL_HINTS = (
    "vethernet", "wsl", "hyper-v", "vmware", "virtualbox", "loopback",
    "bluetooth", "蓝牙", "tap-", " tailscale", "zerotier", "docker", "npcap",
    "vpn", "虚拟",
)

ADAPTER_RE = re.compile(r"^\s*(\S.*(?:adapter|适配器)\s+[^:]+?)\s*:\s*$", re.IGNORECASE)
GATEWAY_RE = re.compile(r"(网关|gateway)", re.IGNORECASE)
IPV4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


def _is_virtual(adapter: str) -> bool:
    low = adapter.lower()
    return any(h in low for h in VIRTUAL_HINTS)


def enumerate_ipv4() -> list[dict]:
    """枚举本机 IPv4，带上适配器名、子网掩码、是否虚拟网卡、所在网段。

    关键点：**网关行必须整行跳过**。否则 `默认网关 . . . : 10.180.0.1`
    会被正则抓成本机地址，用户照着输 URL 会连到路由器上。
    """
    entries: list[dict] = []

    if is_windows():
        out = sh(["ipconfig"])
        current = "unknown"
        in_gateway_block = False
        for line in out.splitlines():
            m = ADAPTER_RE.match(line)
            if m:
                current = m.group(1).strip()
                in_gateway_block = False
                continue
            if GATEWAY_RE.search(line):
                in_gateway_block = True
                continue

            stripped = line.strip()
            if in_gateway_block:
                # ipconfig 的网关会折行：标签行之后跟一行纯 IP（IPv6 下面那行 IPv4）
                if not stripped or re.fullmatch(r"[0-9a-fA-F:.%]+", stripped):
                    continue
                in_gateway_block = False

            mip = IPV4_RE.search(line)
            if not mip:
                continue
            ip = mip.group(1)
            if ip.startswith("255."):
                # 子网掩码，挂到本节上一条地址
                if entries and entries[-1]["adapter"] == current and entries[-1]["mask"] is None:
                    entries[-1]["mask"] = ip
                continue
            if ip in ("0.0.0.0", "127.0.0.1"):
                continue
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                continue
            entries.append({"ip": ip, "adapter": current, "mask": None})
    else:
        out = sh(["ip", "-4", "addr"])
        current = "unknown"
        for line in out.splitlines():
            m = re.match(r"^\d+:\s+([^:@]+)", line)
            if m:
                current = m.group(1).strip()
                continue
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if m:
                ip, plen = m.group(1), int(m.group(2))
                mask = str(ipaddress.IPv4Network(f"0.0.0.0/{plen}").netmask)
                entries.append({"ip": ip, "adapter": current, "mask": mask})

    # 去重 + 补算网段 + 标注虚拟网卡
    seen: set[str] = set()
    result: list[dict] = []
    for e in entries:
        if e["ip"] in seen:
            continue
        seen.add(e["ip"])
        net = None
        if e["mask"]:
            try:
                net = str(ipaddress.IPv4Network(f"{e['ip']}/{e['mask']}", strict=False))
            except ValueError:
                pass
        e["network"] = net
        e["virtual"] = _is_virtual(e["adapter"])
        result.append(e)
    return result


def all_ipv4_addresses() -> list[str]:
    return [e["ip"] for e in enumerate_ipv4()]


def global_ipv6_addresses() -> list[str]:
    """挑出真正可用于公网直连的 IPv6。

    排除：link-local (fe80::/10)、unique-local (fc00::/7)、loopback。
    """
    out: list[str] = []
    if is_windows():
        raw = sh(["ipconfig"])
        cands = re.findall(r"\b([0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){2,7})\b", raw)
    else:
        raw = sh(["ip", "-6", "addr"])
        cands = re.findall(r"inet6\s+([0-9a-fA-F:]+)/", raw)

    for c in cands:
        try:
            ip = ipaddress.IPv6Address(c)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_multicast:
            continue
        if ip in ipaddress.ip_network("fc00::/7"):
            continue
        s = str(ip)
        if s not in out:
            out.append(s)
    return out


def classify(ip: str) -> str:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if a.version == 6:
        return "public-v6" if not a.is_private else "private-v6"
    if a.is_loopback:
        return "loopback"
    if a.is_link_local:
        return "link-local"
    if a in CGNAT:
        return "cgnat"
    if a.is_private:
        return "private"
    return "public-v4"


# ---------------------------------------------------------------- 各项检测

def detect_tailscale(ips: list[str], v6s: list[str]) -> dict:
    """Tailscale 用 100.64.0.0/10 + fd7a:115c:a1e0::/48。"""
    ts_v4 = [ip for ip in ips if classify(ip) == "cgnat"]
    ts_v6 = [ip for ip in v6s if ip.startswith("fd7a:115c:a1e0")]
    cli = sh(["tailscale", "status", "--json"], timeout=5)
    running = bool(cli and cli.strip().startswith("{"))
    ip_hint = None
    if running:
        try:
            ip_hint = json.loads(cli).get("Self", {}).get("TailscaleIPs")
        except Exception:
            pass
    return {
        "detected": bool(ts_v4 or ts_v6 or running),
        "cli": running,
        "ipv4": ts_v4,
        "ipv6": ts_v6,
        "reported_ips": ip_hint,
    }


def _mdns_packet() -> bytes:
    """手搓一个 mDNS PTR 查询（_services._dns-sd._udp.local）。"""
    header = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    qname = b""
    for label in ("_services", "_dns-sd", "_udp", "local"):
        qname += bytes([len(label)]) + label.encode()
    qname += b"\x00"
    return header + qname + struct.pack("!HH", 12, 1)


def check_mdns(timeout: float = 1.5) -> dict:
    """mDNS 能否收到回应。

    校园网常把 5353 干掉。它不影响我们的主链路（我们用 IP 直连），
    但影响「自动发现 PC」这个便利功能，所以要测。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(timeout)
        s.sendto(_mdns_packet(), (MDNS_GROUP, MDNS_PORT))
        responders = set()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                _, addr = s.recvfrom(2048)
                responders.add(addr[0])
            except socket.timeout:
                break
            except OSError:
                break
        return {"works": bool(responders), "responders": sorted(responders)}
    except OSError as e:
        return {"works": False, "responders": [], "error": str(e)}
    finally:
        s.close()


def check_tcp_bind(port: int) -> dict:
    """能否在 0.0.0.0 上监听该 TCP 端口。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if is_windows():
            # 避免 TIME_WAIT 干扰，也让「端口被别的进程占」能被准确检出
            s.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", socket.SO_REUSEADDR), 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        return {"port": port, "free": True}
    except OSError as e:
        return {"port": port, "free": False, "error": str(e)}
    finally:
        s.close()


def check_udp_bind(port: int) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        return {"port": port, "free": True}
    except OSError as e:
        return {"port": port, "free": False, "error": str(e)}
    finally:
        s.close()


def check_firewall() -> dict:
    """Windows 防火墙状态。只读，不修改任何系统设置。"""
    if not is_windows():
        return {"applicable": False}
    out = sh(["netsh", "advfirewall", "show", "allprofiles", "state"], timeout=6)
    if not out:
        return {"applicable": True, "readable": False}
    on = len(re.findall(r"(ON|开启|启用)", out, re.IGNORECASE))
    off = len(re.findall(r"(OFF|关闭)", out, re.IGNORECASE))
    return {"applicable": True, "readable": True, "profiles_on": on, "profiles_off": off}


def probe_peer(spec: str, timeout: float = 2.0) -> dict:
    """测某个 对端:端口 的 TCP 可达性。"""
    if ":" not in spec:
        return {"target": spec, "error": "格式应为 host:port"}
    host, _, port_s = spec.rpartition(":")
    try:
        port = int(port_s)
    except ValueError:
        return {"target": spec, "error": "端口不是数字"}

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(family, socket.SOCK_STREAM)
    s.settimeout(timeout)
    t0 = time.perf_counter()
    try:
        s.connect((host, port))
        rtt = (time.perf_counter() - t0) * 1000
        return {"target": spec, "reachable": True, "rtt_ms": round(rtt, 1)}
    except Exception as e:
        return {"target": spec, "reachable": False, "error": str(e)}
    finally:
        s.close()


# ---------------------------------------------------------------- 结论

def verdict(result: dict) -> list[tuple[str, str, str]]:
    """根据探测结果给出建议路径。返回 [(等级, 内容, 颜色)]。"""
    lines: list[tuple[str, str, str]] = []
    adapters = result.get("adapters", [])
    phys = [a for a in adapters if not a.get("virtual")]
    v6s = result["ipv6_global"]
    ts = result["tailscale"]

    private_net = next(
        (a for a in phys if classify(a["ip"]) == "private" and a.get("network")), None
    )

    if ts["detected"]:
        lines.append(("PASS", "Tailscale 已在线 —— ③ WireGuard 打洞可用，这是最省心的一档", "green"))
    if v6s:
        lines.append(("PASS", f"有公网 IPv6（{v6s[0]}）—— ② 有希望，但要实测是否允许入站", "green"))

    if private_net:
        lines.append((
            "INFO",
            f"物理网卡在 {private_net['network']} —— 手机若也在这个网段，① 才有意义",
            "yellow",
        ))
    elif any(classify(a["ip"]) == "private" for a in phys):
        lines.append(("INFO", "有私有网段地址 —— ① 理论可行，需实测客户端隔离", "yellow"))

    if not phys:
        lines.append(("WARN", "只找到虚拟网卡地址 —— 检查 Wi-Fi 是否已连接/启用", "red"))
    elif not ts["detected"] and not v6s and private_net:
        lines.append((
            "WARN",
            "只有私有 IPv4、无覆盖网、无公网 IPv6 —— 校园网一开隔离就只能靠 ④ 中继或热点兜底",
            "red",
        ))

    lines.append(("NEXT", "以上只能排除明显死路；能不能连上必须用 beacon.py 实测", "dim"))
    return lines


# ---------------------------------------------------------------- 报告

def render_console(result: dict) -> None:
    print()
    print(_c("═" * 62, DIM))
    print(_c("  多端 DCS 外设 · 网络探测", BOLD))
    print(_c("═" * 62, DIM))
    print(f"  时间      {result['timestamp']}")
    print(f"  系统      {result['os']}")
    print(f"  主机名    {result['hostname']}")
    print()

    print(_c("· 地址", BOLD))
    print(f"  默认网关  {result['gateway'] or '—'}")
    for a in result.get("adapters", []):
        net = f"  网段 {a['network']}" if a.get("network") else ""
        tag = _c("  [虚拟网卡·手机连不上]", DIM) if a["virtual"] else ""
        print(f"  {a['ip']:<16}{a['adapter'][:30]}{net}{tag}")
    for ip in result["ipv6_global"]:
        print(f"  {ip:<44} 公网 IPv6 · 需实测入站")
    print()

    ts = result["tailscale"]
    print(_c("· 覆盖网", BOLD))
    if ts["detected"]:
        print("  " + ok(f"Tailscale 在线 {ts['ipv4'] or ts['ipv6'] or ''}"))
    else:
        print("  " + warn("未检测到 Tailscale（若校园网隔离，这可能是你唯一的直连出路）"))
    print()

    md = result["mdns"]
    print(_c("· 发现能力", BOLD))
    if md["works"]:
        print("  " + ok(f"mDNS 可用，收到 {len(md['responders'])} 个响应"))
    else:
        print("  " + warn("mDNS 无响应 —— 自动发现不可用，需要手动输 IP 或扫码"))
    print()

    print(_c("· 端口占用", BOLD))
    for r in result["ports"]["tcp"]:
        mark = ok if r["free"] else warn
        print("  " + mark(f"TCP {r['port']}  " + ("可监听" if r["free"] else f"被占用 ({r.get('error','')})")))
    for r in result["ports"]["udp"]:
        mark = ok if r["free"] else warn
        print("  " + mark(f"UDP {r['port']}  " + ("可绑定" if r["free"] else f"被占用 ({r.get('error','')})")))
    print()

    fw = result["firewall"]
    if fw.get("applicable"):
        print(_c("· 防火墙", BOLD))
        if fw.get("readable"):
            print(f"  已开启的配置文件数 {fw.get('profiles_on', 0)}，关闭的 {fw.get('profiles_off', 0)}")
            if fw.get("profiles_on", 0) > 0:
                print("  " + warn("有配置文件处于开启状态，首次监听时 Windows 会弹授权框，记得选「专用网络」"))
        else:
            print("  " + warn("无法读取防火墙状态（可能需要管理员），请手动确认"))
        print()

    if result.get("peer"):
        print(_c("· 对端探测", BOLD))
        p = result["peer"]
        if p.get("reachable"):
            print("  " + ok(f"{p['target']} 可达，RTT {p['rtt_ms']} ms"))
        else:
            print("  " + bad(f"{p['target']} 不可达：{p.get('error')}"))
        print()

    print(_c("· 结论", BOLD))
    for kind, text, color in verdict(result):
        prefix = {"PASS": "  ", "INFO": "  ", "WARN": "  ", "NEXT": "  "}[kind]
        paint = {"green": GREEN, "yellow": YELLOW, "red": RED, "dim": DIM}[color]
        print(_c(prefix + text, paint))
    print()
    print(_c("═" * 62, DIM))
    print()


def render_markdown(result: dict) -> str:
    lines = [
        "# 网络探测报告",
        "",
        f"> 由 `tools/netprobe.py` 于 {result['timestamp']} 自动生成。重新运行会覆盖本文件。",
        "",
        "## 环境",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 系统 | {result['os']} |",
        f"| 主机名 | `{result['hostname']}` |",
        f"| 主出口 IP | `{result['primary_ip']}` |",
        f"| 默认网关 | `{result['gateway']}` |",
        "",
        "## 地址清单",
        "",
        "| 地址 | 类型 | 适配器 | 网段 | 用途 |",
        "|---|---|---|---|---|",
    ]
    for a in result.get("adapters", []):
        t = classify(a["ip"])
        use = {
            "private": "① 同网段直连候选",
            "cgnat": "③ Tailscale",
            "public-v4": "公网",
            "link-local": "—",
        }.get(t, t)
        if a["virtual"]:
            use = "虚拟网卡，跳过"
        net = a.get("network") or "—"
        lines.append(f"| `{a['ip']}` | {t} | `{a['adapter']}` | {net} | {use} |")
    for ip in result["ipv6_global"]:
        lines.append(f"| `{ip}` | public-v6 | — | — | ② IPv6 直连候选 |")
    if not result["ipv4"] and not result["ipv6_global"]:
        lines.append("| — | — | — | — | 未检到可用地址 |")

    lines += [
        "",
        "## 检测结果",
        "",
        "| 检测项 | 结果 | 说明 |",
        "|---|---|---|",
        f"| Tailscale | {'在线' if result['tailscale']['detected'] else '未检测到'} | "
        f"{'、'.join(result['tailscale']['ipv4'] + result['tailscale']['ipv6']) or '—'} |",
        f"| mDNS | {'可用' if result['mdns']['works'] else '无响应'} | "
        f"影响自动发现，不影响主链路 |",
        f"| 公网 IPv6 | {'有' if result['ipv6_global'] else '无'} | ② 档的前提 |",
    ]
    fw = result["firewall"]
    lines.append(
        f"| Windows 防火墙 | {('开启 ' + str(fw.get('profiles_on', 0)) + ' 个配置文件') if fw.get('applicable') else '不适用'} | "
        f"首次监听需授权 |"
    )

    lines += ["", "## 端口", "", "| 端口 | 协议 | 状态 |", "|---|---|---|"]
    for r in result["ports"]["tcp"]:
        lines.append(f"| {r['port']} | TCP | {'空闲' if r['free'] else '被占用'} |")
    for r in result["ports"]["udp"]:
        lines.append(f"| {r['port']} | UDP | {'空闲' if r['free'] else '被占用'} |")

    if result.get("peer"):
        p = result["peer"]
        lines += ["", "## 对端探测", ""]
        if p.get("reachable"):
            lines.append(f"- ✅ `{p['target']}` 可达，RTT **{p['rtt_ms']} ms**")
        else:
            lines.append(f"- ❌ `{p['target']}` 不可达：{p.get('error')}")

    lines += ["", "## 结论", ""]
    for kind, text, _ in verdict(result):
        bullet = {"PASS": "- ✅", "INFO": "- ℹ️", "WARN": "- ⚠️", "NEXT": "- ➡️"}[kind]
        lines.append(f"{bullet} {text}")

    lines += [
        "",
        "## 下一步",
        "",
        "```bash",
        "# 1) 在 PC 上起一个可达性信标",
        "python tools/beacon.py --port 8080",
        "",
        "# 2) 手机浏览器打开控制台打印出来的任意一个 URL",
        "#    页面能打开 = 链路通；页面显示 RTT 和丢包 = 可以继续下一步",
        "```",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程

def run_probe(peer: str | None = None) -> dict:
    adapters = enumerate_ipv4()
    p = primary_ip()
    if p and not any(a["ip"] == p for a in adapters):
        adapters.insert(0, {
            "ip": p, "adapter": "primary-route", "mask": None,
            "network": None, "virtual": False,
        })
    ips = [a["ip"] for a in adapters]

    if is_windows():
        gw, _ = _windows_gateway_and_ip()
    else:
        gw = _posix_gateway()

    v6s = global_ipv6_addresses()

    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "os": f"{platform.system()} {platform.release()}"
              + (" (WSL)" if is_wsl() else "")
              + f" · Python {platform.python_version()}",
        "hostname": socket.gethostname(),
        "primary_ip": p,
        "gateway": gw,
        "adapters": adapters,
        "ipv4": ips,
        "ipv6_global": v6s,
        "tailscale": detect_tailscale(ips, v6s),
        "mdns": check_mdns(),
        "ports": {
            "tcp": [check_tcp_bind(port) for port in PROBE_PORTS_TCP],
            "udp": [check_udp_bind(port) for port in PROBE_PORTS_UDP],
        },
        "firewall": check_firewall(),
    }
    if peer:
        result["peer"] = probe_peer(peer)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="多端 DCS 外设 · 网络探测")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    ap.add_argument("--peer", metavar="HOST:PORT", help="额外探测某个对端是否可达")
    ap.add_argument("--no-report", action="store_true", help="不写 docs/NETWORK-PROBE.md")
    ap.add_argument("--out", default="docs/NETWORK-PROBE.md", help="报告输出路径")
    args = ap.parse_args()

    result = run_probe(args.peer)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_console(result)

    if not args.no_report and not args.json:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(result), encoding="utf-8")
        print(_c(f"报告已写入 {out}", DIM))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""生成本地 CA 与服务端证书，并导出一份 iPad 能装的描述文件。

为什么需要这个：iOS 13 起，**传感器（陀螺仪 / 方向）只在安全上下文里可用**
（https 或 localhost）。WebKit 工程师的原话见 https://webkit.org/b/203287#c5 ：
"changed behavior in iOS 13 to require a secure context (file protocol, https or
loopback), no HTTP"。所以 `http://192.168.50.1:8080/yoke` 上体感永远拿不到数据 ——
这不是代码问题，换 HTTPS 才有得谈。

用局域网 IP 又不可能有公信证书，于是走「本地 CA + 给 iPad 装一次根证书」：
装了之后 https 不再报警告，且「添加到主屏幕」的 standalone 窗口也能正常加载
（自签证书在 standalone 里连"继续访问"的按钮都没有，会直接白屏，所以必须装 CA）。

用法：
    python tools/make-cert.py                       # 自动收集本机 IPv4 + 常用固定 IP
    python tools/make-cert.py --ip 192.168.50.1     # 追加要签进证书的 IP
    python tools/make-cert.py --force               # 连 CA 一起重签（iPad 上要重装描述文件）

产物（tools/certs/，已 gitignore —— 私钥不该进仓库）：
    ca.crt / ca.key                 根证书与私钥
    server.crt / server.key         给 beacon 用的服务端证书（SAN 里含上面那些 IP）
    dcs-peripheral-ca.mobileconfig  给 iPad 的描述文件（内嵌 ca.crt）
"""
from __future__ import annotations

import argparse
import base64
import re
import socket
import subprocess
import sys
import uuid
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parent / "certs"
DEFAULT_IPS = [
    "127.0.0.1",
    "192.168.50.1",     # 计划中的：PC 网卡（iPad 直连）
    "192.168.137.1",    # Windows 移动热点
    "172.20.10.2",      # 万一以后用蜂窝版 USB 共享
]


def run(*args: str) -> None:
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"[x] {' '.join(args)}\n{p.stderr.strip()}")


def local_ipv4() -> list[str]:
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))          # 不真发包，只为让内核选出口地址
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    out = []
    for ip in ips:
        if ip not in out and not ip.startswith("169.254."):
            out.append(ip)
    return out


def make_ca(force: bool) -> None:
    crt, key = CERT_DIR / "ca.crt", CERT_DIR / "ca.key"
    if crt.exists() and key.exists() and not force:
        print("  [=] 复用已有 CA（要重签加 --force）")
        return
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(crt), "-days", "3650",
        "-subj", "/CN=DCS Peripheral Local CA/O=DCS Peripheral",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    print(f"  [+] 新 CA -> {crt.name}")


def make_server(ips: list[str]) -> None:
    key, csr = CERT_DIR / "server.key", CERT_DIR / "server.csr"
    crt = CERT_DIR / "server.crt"
    ext = CERT_DIR / "server.ext"

    run("openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(csr),
        "-subj", "/CN=dcs-peripheral")

    san = ",".join([f"IP:{ip}" for ip in ips] + ["DNS:dcs.local", "DNS:localhost"])
    ext.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName={san}\n",
        encoding="utf-8",
    )

    run("openssl", "x509", "-req", "-in", str(csr),
        "-CA", str(CERT_DIR / "ca.crt"), "-CAkey", str(CERT_DIR / "ca.key"),
        "-CAcreateserial", "-out", str(crt), "-days", "3650",
        "-sha256", "-extfile", str(ext))
    csr.unlink(missing_ok=True)
    print(f"  [+] 服务端证书 -> {crt.name}  SAN: {san}")


def der_b64(pem: Path) -> str:
    p = subprocess.run(["openssl", "x509", "-in", str(pem), "-outform", "der"],
                       capture_output=True)
    if p.returncode != 0:
        sys.exit("[x] PEM -> DER 失败")
    b64 = base64.b64encode(p.stdout).decode("ascii")
    return "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))


def make_mobileconfig() -> Path:
    """把根证书打成 iPad 能直接装的 .mobileconfig（PayloadType=root）。"""
    payload = der_b64(CERT_DIR / "ca.crt")
    u1, u2 = str(uuid.uuid4()).upper(), str(uuid.uuid4()).upper()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadCertificateFileName</key><string>ca.crt</string>
      <key>PayloadContent</key>
      <data>
{payload}
      </data>
      <key>PayloadDescription</key><string>DCS 外设本地根证书</string>
      <key>PayloadDisplayName</key><string>DCS Peripheral Local CA</string>
      <key>PayloadIdentifier</key><string>local.dcs.peripheral.ca.{u2}</string>
      <key>PayloadType</key><string>com.apple.security.root</string>
      <key>PayloadUUID</key><string>{u2}</string>
      <key>PayloadVersion</key><integer>1</integer>
    </dict>
  </array>
  <key>PayloadDescription</key>
  <string>让 iPad 信任本机 beacon 的 HTTPS 证书（体感/陀螺仪需要 https 才给数据）</string>
  <key>PayloadDisplayName</key><string>DCS Peripheral 本地 CA</string>
  <key>PayloadIdentifier</key><string>local.dcs.peripheral.profile.{u1}</string>
  <key>PayloadOrganization</key><string>DCS Peripheral</string>
  <key>PayloadRemovalDisallowed</key><false/>
  <key>PayloadType</key><string>Configuration</string>
  <key>PayloadUUID</key><string>{u1}</string>
  <key>PayloadVersion</key><integer>1</integer>
</dict>
</plist>
"""
    out = CERT_DIR / "dcs-peripheral-ca.mobileconfig"
    out.write_text(xml, encoding="utf-8")
    print(f"  [+] 描述文件 -> {out.name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="生成本地 CA / 服务端证书 / iPad 描述文件")
    ap.add_argument("--ip", action="append", default=[],
                    help="额外签进证书的 IP（可重复）")
    ap.add_argument("--force", action="store_true", help="连 CA 一起重签")
    args = ap.parse_args()

    CERT_DIR.mkdir(parents=True, exist_ok=True)

    ips: list[str] = []
    for ip in DEFAULT_IPS + local_ipv4() + args.ip:
        ip = ip.strip()
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip) and ip not in ips:
            ips.append(ip)

    print(f"  证书目录 {CERT_DIR}")
    make_ca(args.force)
    make_server(ips)
    mc = make_mobileconfig()

    print()
    print("  下一步（iPad 上做一次，页面会带着走）：")
    print("    1) iPad 打开 http://<PC的IP>:8080/yoke → 点「体感」→ 会弹出引导页")
    print("    2) 点页面上那个「下载根证书」（= /ca.mobileconfig，不用 AirDrop/邮件）")
    print("    3) 设置 → 通用 → VPN 与设备管理 → 安装（提示「未签名」是正常的）")
    print("    4) 设置 → 通用 → 关于本机 → 证书信任设置 → 打开「DCS Peripheral Local CA」")
    print("    5) 打开 https://<PC的IP>:8443/yoke ，地址栏应无警告")
    print(f"       （描述文件就在 {mc}，要手动传也行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

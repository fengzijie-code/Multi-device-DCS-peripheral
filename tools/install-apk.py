"""把刚编译好的 debug APK 装到已连接的 Android 设备上。

为什么单独写一个脚本，而不是让你敲 adb 命令：
  1. adb 的路径在每个机器上都不一样，写死在文档里迟早过时；
  2. `adb install` 失败时的几种报错（没设备 / 未授权 / 签名冲突）长得都很像，
     脚本能直接告诉你是哪一种，省一轮猜。

用法：
    python tools/install-apk.py            # 装最新的 debug APK
    python tools/install-apk.py --list     # 只看设备列表，不装

注意：安装会重启 App，摇杆会断一两秒（vjoy_out 的看门狗会把杆回中）。
飞行中别装，等落地。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
APK = ROOT / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"

# 常见 adb 位置。找不到就让用户自己指定 ADB 环境变量。
CANDIDATES = [
    Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
    Path("C:/Android/Sdk/platform-tools/adb.exe"),
    Path("D:/Android/Sdk/platform-tools/adb.exe"),
    Path("D:/Android Studio/Sdk/platform-tools/adb.exe"),
]


def find_adb() -> str:
    import os

    env = os.environ.get("ADB")
    if env and Path(env).exists():
        return env
    for p in CANDIDATES:
        if p.exists():
            return str(p)
    # 最后试 PATH
    try:
        subprocess.run(["adb", "version"], capture_output=True, timeout=10, check=True)
        return "adb"
    except Exception:
        pass
    raise SystemExit(
        "[x] 找不到 adb。请把 Android SDK 的 platform-tools 加到 PATH，\n"
        "    或者设一个环境变量 ADB 指向 adb.exe。"
    )


def run(adb: str, *args: str, timeout: float = 90.0) -> tuple[int, str]:
    try:
        r = subprocess.run([adb, *args], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return -1, "超时"
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    return r.returncode, out


def device_list(adb: str) -> tuple[int, str]:
    """拿设备列表；adb 服务僵死时自动重启它。

    踩过的坑：adb server 会僵死 —— 进程还在、5037 还在监听，但客户端连上去
    就永远不返回。表现是「双击后一点反应都没有」：没有报错、没有输出，因为
    第一个 adb 调用就挂在那里等。这时候任何 adb 子命令都没用（包括
    `adb kill-server`，它同样要先连上那个僵死的 server），只能从外部杀进程。

    所以这里用 taskkill 而不是 adb kill-server，然后重试一次。
    """
    rc, out = run(adb, "devices", timeout=20)
    if rc != -1:
        return rc, out

    print("[!] adb 没响应了（服务僵死），正在从外部重启它…")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, timeout=20)
    except Exception as e:
        print(f"    taskkill 失败：{e}")
    time.sleep(1.5)
    rc, out = run(adb, "devices", timeout=60)
    if rc == 0:
        print("[✓] adb 服务已重启")
    else:
        print("[x] 重启后仍然不通。拔插一次数据线，或者重装 Android SDK 的 platform-tools。")
    return rc, out


def main() -> int:
    ap = argparse.ArgumentParser(description="安装 debug APK 到已连接设备")
    ap.add_argument("--list", action="store_true", help="只列出设备，不安装")
    args = ap.parse_args()

    adb = find_adb()
    print(f"  adb    {adb}")

    rc, out = device_list(adb)
    if rc != 0:
        print(f"[x] adb devices 失败：{out}")
        return 2

    # adb devices 的第一行是标题，其余每行 "<serial>\t<state>"
    lines = [ln for ln in out.splitlines()[1:] if ln.strip()]
    devices = [ln.split() for ln in lines]
    ready = [d[0] for d in devices if len(d) >= 2 and d[1] == "device"]
    unauth = [d[0] for d in devices if len(d) >= 2 and d[1] == "unauthorized"]

    if not devices:
        print("[x] 没检测到设备。检查：数据线是不是只有充电功能、USB 调试有没有开。")
        return 2
    if unauth:
        print(f"[!] 有设备未授权：{', '.join(unauth)}")
        print("    在手机上点「允许 USB 调试」那个弹窗，勾上「一律允许」再跑一次。")
    if args.list:
        for d in devices:
            print(f"  {d[0]}  {d[1] if len(d) > 1 else '?'}")
        return 0 if ready else 2
    if not ready:
        print("[x] 没有处于 device 状态的设备，装不了。")
        return 2

    if not APK.exists():
        print(f"[x] APK 不存在：{APK}")
        print("    先在 android/ 目录里跑 gradlew assembleDebug。")
        return 2

    size = APK.stat().st_size / 1024 / 1024
    print(f"  APK    {APK.name}  {size:.1f} MB")
    print(f"  目标   {ready[0] if len(ready) == 1 else ', '.join(ready)}")
    print("  安装中（会重启 App，摇杆断一两秒）…")

    cmd = ["install", "-r", str(APK)]
    if len(ready) > 1:
        cmd = ["-s", ready[0], *cmd]
    rc, out = run(adb, *cmd, timeout=180)

    if rc == 0 and "Success" in out:
        print("[✓] 装好了。打开 App，顶部应该能看到「仪表 / 起降 / 战斗 / 校准」四个标签。")
        return 0

    if rc == -1:
        print("[x] 安装卡住超时（adb 可能又僵死了）。重跑一次脚本，它会自己重启 adb。")
        return 1

    # 把最常见的三种失败翻译成人话
    print(f"[x] 安装失败：{out}")
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out or "signatures do not match" in out:
        print("    签名不一致：手机上装的是别的机器签的包。先卸载再装：")
        print(f"    adb uninstall com.fengzijie.dcsperipheral")
    elif "INSTALL_FAILED_VERSION_DOWNGRADE" in out:
        print("    版本号比手机上的旧。改 versionCode 或者先卸载。")
    elif "no devices" in out.lower():
        print("    设备掉了，重新插一下数据线。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

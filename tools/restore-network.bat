@echo off
REM ============================================================
REM  DCS Peripheral - undo wired-direct changes on this PC
REM
REM  For people who tried the wired-direct setup (v1.4.1) and want
REM  their PC back to the wireless-first state:
REM
REM    1. Firewall: rule "DCS Peripheral Bridge" back to TCP 8080,8443
REM       only (removes the 80/TCP + 53/UDP entries used by captive.py).
REM    2. IP: removes the static 192.168.77.1/24 that
REM       tools\set-static-ip.bat (v1.4.1) put on the wired adapter,
REM       re-enables DHCP. Without a DHCP server the adapter falls
REM       back to a 169.254.x.x self-assigned address - same as before.
REM
REM  Interface: index 49 (ASIX AX88179 USB adapter) - the iPad wired
REM  link. If you replugged adapters and the index changed, run
REM    powershell: Get-NetAdapter | Format-Table ifIndex,Name
REM  and edit the two commands below.
REM
REM  Run: double-click (it elevates itself via UAC). One-time - after
REM  this, plain "tools\start-ipad.bat" over Wi-Fi is all you need.
REM ============================================================

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [*] Requesting administrator rights - approve the UAC prompt.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo [*] Restoring firewall rule to TCP 8080,8443 only ...
powershell -NoProfile -Command ^
  "netsh advfirewall firewall delete rule name='DCS Peripheral Bridge' | Out-Null; netsh advfirewall firewall add rule name='DCS Peripheral Bridge' dir=in action=allow protocol=TCP localport=8080,8443 profile=private,public | Out-Null; Write-Host '[OK] firewall = TCP 8080,8443 (captive 80/TCP + 53/UDP removed)'"

echo [*] Removing static 192.168.77.1/24 from interface #49, re-enabling DHCP ...
powershell -NoProfile -Command ^
  "Remove-NetIPAddress -InterfaceIndex 49 -IPAddress 192.168.77.1 -Confirm:$false -ErrorAction SilentlyContinue; Set-NetIPInterface -InterfaceIndex 49 -Dhcp Enabled -AddressFamily IPv4 -ErrorAction SilentlyContinue; Start-Sleep 2; Get-NetIPAddress -InterfaceIndex 49 -AddressFamily IPv4 | Format-Table IPAddress,PrefixLength -AutoSize"

echo.
echo [OK] PC restored to the wireless-first state.
echo      - Unplug the cable (the iPad ethernet config goes with it).
echo      - Restart tools\start-ipad.bat (a running instance still
echo        holds the old captive responder on port 80/53).
echo      - iPad: open the address printed by start-ipad.bat over Wi-Fi.
echo.
echo      Want wired back later? See release/v1.4.1/RELEASE.md - or run
echo      tools\start-ipad.bat --captive after redoing the static IP.
pause

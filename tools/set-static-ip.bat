@echo off
REM ============================================================
REM  DCS Peripheral - give the iPad direct-ethernet link fixed IPs
REM
REM  Why:
REM    Direct cable between iPad and this PC has no DHCP, so both
REM    ends self-assign 169.254.x.x (APIPA). iOS is unreliable with
REM    APIPA ("no network"), so we pin a proper private subnet:
REM
REM      PC  (interface #49, ASIX AX88179 USB adapter)  192.168.77.1/24
REM      iPad (Settings > Ethernet > Configure IP > Manual) 192.168.77.2/24
REM
REM  Run:  double-click this file (it elevates itself via UAC).
REM  Next: run tools\start-ipad.bat - it re-signs the cert with the
REM        new IP automatically. Then open on the iPad:
REM        https://192.168.77.1:8443/yoke
REM
REM  Undo:
REM    powershell: Remove-NetIPAddress -InterfaceIndex 49 -IPAddress 192.168.77.1
REM ============================================================

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [*] Requesting administrator rights - approve the UAC prompt.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo [*] Setting static IP 192.168.77.1/24 on interface #49 (Ethernet 4)...

powershell -NoProfile -Command ^
  "try { New-NetIPAddress -InterfaceIndex 49 -IPAddress 192.168.77.1 -PrefixLength 24 -ErrorAction Stop | Out-Null; Write-Host '[OK] 192.168.77.1/24 added' } catch { if ($_.Exception.Message -like '*already*') { Write-Host '[OK] already set' } else { Write-Host ('[x] ' + $_.Exception.Message); exit 1 } }; Remove-NetIPAddress -InterfaceIndex 49 -IPAddress 169.254.* -Confirm:$false -ErrorAction SilentlyContinue"

if errorlevel 1 (
    echo.
    echo [x] Failed to set the IP. Nothing was changed.
    pause
    exit /b 1
)

echo.
echo [OK] PC side done. Current IPv4 on interface #49:
powershell -NoProfile -Command "Get-NetIPAddress -InterfaceIndex 49 -AddressFamily IPv4 | Format-Table IPAddress,PrefixLength -AutoSize"

echo ============================================================
echo  Now on the iPad (Settings ^> Ethernet):
echo    1. Configure IP -^> Manual
echo       IP:     192.168.77.2
echo       Mask:   255.255.255.0
echo       Router: 192.168.77.1
echo    2. Configure DNS -^> Manual -^> 192.168.77.1
echo       (the captive.py probe responder answers DNS on this PC;
echo        without it iOS marks the link "no network" and Safari
echo        refuses to send anything over the cable)
echo    3. Run tools\open-firewall.bat once as admin (ports 80/53)
echo    4. Run tools\start-ipad.bat on this PC (re-signs cert)
echo    5. Safari on iPad:  https://192.168.77.1:8443/yoke
echo ============================================================
pause

@echo off
REM ============================================================
REM  DCS Peripheral - one-click dev startup (USB path)
REM
REM  Opens four console windows:
REM    dcs-beacon    the bridge service (HTTP :8080 + telemetry UDP :5010)
REM    dcs-watchdog  keeps `adb reverse` alive, prints a heartbeat every 30s
REM    dcs-mock      fake telemetry at 60 Hz
REM    dcs-vjoy      phone tilt -> virtual joystick (watchdog: centre on silence)
REM
REM  Using real DCS instead of the mock:
REM    close the "dcs-mock" window only -- keep the others running.
REM
REM  Stop everything: close the four windows.
REM ============================================================

setlocal
cd /d "%~dp0.."

set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"

if not exist "%ADB%" (
    echo [x] adb not found at "%ADB%"
    echo     Check that Android Studio / SDK is installed.
    pause
    exit /b 1
)

echo.
echo [1/6] Looking for a connected device...
"%ADB%" devices
echo.
echo       If the list is empty or says "unauthorized",
echo       enable USB debugging and accept the RSA prompt first.
echo.
pause

echo [2/6] Starting bridge (:8080) ...
start "dcs-beacon" cmd /c "python -u tools\beacon.py --port 8080 --ipv4-only"
timeout /t 2 >nul

echo [3/6] Starting USB watchdog ...
echo       It re-creates `adb reverse` whenever adb restarts.
start "dcs-watchdog" cmd /c "python -u tools\usb-watchdog.py --interval 2"
timeout /t 1 >nul

echo [4/6] Starting mock telemetry (60 Hz) ...
echo       Close this window when you want real DCS data instead.
start "dcs-mock" cmd /c "python -u tools\mock_export.py --profile maneuver --rate 60"
timeout /t 1 >nul

echo [5/6] Starting virtual joystick output ...
echo       Needs vJoy installed. Without it the window will say so and exit.
start "dcs-vjoy" cmd /c "python -u tools\vjoy_out.py --id 1 --port 5011 & pause"
timeout /t 1 >nul

echo [6/6] Launching the app ...
"%ADB%" reverse tcp:8080 tcp:8080
"%ADB%" shell am force-stop com.fengzijie.dcsperipheral
"%ADB%" shell am start -n com.fengzijie.dcsperipheral/.MainActivity

echo.
echo Done.
echo   App should show "已连接" with RTT 2-4 ms.
echo   If it shows data frozen, read the dcs-watchdog heartbeat:
echo     - "no data age=..."     -^> DCS is not running / not in a mission
echo     - "bridge not answering" -^> the dcs-beacon window died
echo.
echo   Yoke page: tap "校零", then "解锁". If it says
echo   "PC 端虚拟摇杆未运行", the dcs-vjoy window is not running.
echo.
pause

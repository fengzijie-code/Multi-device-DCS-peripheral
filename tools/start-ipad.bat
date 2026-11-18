@echo off
REM ============================================================
REM  DCS Peripheral - iPad only (no phone, no adb)
REM
REM  Use this instead of start-usb.bat when the phone is not part
REM  of the setup: the iPad opens http://<this PC>:8080/yoke.
REM
REM  This file is intentionally ASCII-only. Chinese text in a .bat
REM  gets mangled by the console code page and then every later
REM  line is parsed as a command.
REM
REM  What it skips:  the adb/phone wait, the reverse tunnel, and the
REM                  USB tunnel watchdog (nothing to rebuild)
REM  What it runs:   beacon.py (HTTP + telemetry) and vjoy_out.py
REM
REM  Usage:
REM    start-ipad.bat          normal
REM    start-ipad.bat mock     also start fake 60 Hz telemetry
REM                            (do NOT use while real DCS is running)
REM
REM  Stop: Ctrl+C, then answer Y to "Terminate batch job".
REM        vJoy is reset either way.
REM ============================================================

setlocal EnableExtensions
cd /d "%~dp0.."

set "EXTRA="
if /i "%~1"=="mock" set "EXTRA=--mock"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo.
    echo   [x] Python not found on PATH.
    echo       Install Python 3.9+ and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo.
echo   iPad mode: no phone check, no adb tunnel.
echo   On the iPad open  http://^<this-PC-IP^>:8080/yoke  then
echo   Share - Add to Home Screen.
echo.

%PY% -u tools\run-all.py --no-usb --no-watch %EXTRA%
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo   [!] launcher exited with code %RC%
    pause
)

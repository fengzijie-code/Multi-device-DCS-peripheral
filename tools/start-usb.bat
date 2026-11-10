@echo off
REM ============================================================
REM  DCS Peripheral - one-click startup (USB path)
REM
REM  This file only finds Python and hands over to tools\run-all.py.
REM  Everything else - waiting for the phone, rebuilding the adb
REM  tunnel, port checks, starting and supervising the services -
REM  lives in Python, where it can be tested without double-clicking.
REM
REM  Usage:
REM    start-usb.bat          normal
REM    start-usb.bat mock     also start fake 60 Hz telemetry
REM                           (do NOT use while real DCS is running)
REM
REM  Stop: Ctrl+C, then answer Y to "Terminate batch job".
REM        Or just close this window - vJoy is reset either way.
REM
REM  After a reboot you only need THIS file. The vJoy driver and the
REM  phone app survive reboots; the Python services and the adb tunnel
REM  do not.
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

%PY% -u tools\run-all.py %EXTRA%
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo   [!] launcher exited with code %RC%
    pause
)

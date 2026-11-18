@echo off
REM ============================================================
REM  DCS Peripheral - one-click start (iPad)
REM
REM  This file is intentionally ASCII-only and does almost nothing:
REM  find python, hand the arguments over, keep the window open if
REM  something went wrong. All the real logic and all the messages
REM  live in tools\start.py, which is UTF-8 and can print Chinese.
REM
REM  Why not put the logic here? Chinese text inside a .bat gets
REM  mangled by the console code page, and after the first mangled
REM  line cmd starts parsing the rest as commands. That failure
REM  looks like "the window flashes and disappears".
REM
REM  Usage:
REM    start-ipad.bat              iPad, normal
REM    start-ipad.bat mock         also fake 60 Hz telemetry
REM                                (do NOT use while real DCS runs)
REM    start-ipad.bat phone        phone over USB (adb tunnel)
REM    start-ipad.bat --firewall   add the firewall rule once (UAC)
REM
REM  Stop: Ctrl+C, then answer N at "Terminate batch job" if you
REM        want to read the final lines. vJoy is centered either way.
REM ============================================================

setlocal EnableExtensions
cd /d "%~dp0.."
title DCS Peripheral Bridge

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

if not exist "tools\start.py" (
    echo.
    echo   [x] tools\start.py is missing.
    echo       You are probably running this file from somewhere else.
    echo.
    pause
    exit /b 1
)

%PY% -u tools\start.py %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo   [!] stopped. You can close this window.
) else (
    echo   [!] launcher exited with code %RC% - scroll up for the reason.
)
echo.
pause
exit /b %RC%

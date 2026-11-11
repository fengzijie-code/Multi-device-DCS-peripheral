@echo off
REM ============================================================
REM  DCS Peripheral - install the debug APK to the connected phone
REM
REM  Why a .bat and not "double-click the .py":
REM    1) double-clicking a .py opens and closes a console window
REM       instantly, so you never see the error;
REM    2) "Run as administrator" changes the working directory to
REM       C:\Windows\System32, so every relative path in the script
REM       breaks and it dies before printing anything.
REM  This file pins the directory with %~dp0 and waits at the end.
REM
REM  Usage:
REM    install-apk.bat             install
REM    install-apk.bat --list      only list devices
REM
REM  Do NOT run this while flying: installing restarts the app and
REM  the stick drops out for a second or two.
REM ============================================================

setlocal EnableExtensions
REM The Python script prints Chinese; 65001 makes the console show it.
chcp 65001 >nul
cd /d "%~dp0.."

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

%PY% -u tools\install-apk.py %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo   Done.
) else (
    echo   [!] failed, exit code %RC%
)
REM Always pause: the whole point is that you can read the result.
pause

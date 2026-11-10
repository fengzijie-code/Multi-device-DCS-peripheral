@echo off
REM ============================================================
REM  Record a real DCS session
REM
REM  Opens two windows:
REM    dcs-watchdog  keeps `adb reverse` alive
REM    dcs-recorder  the bridge + recorder (this one is the main window)
REM
REM  Steps:
REM    1. DCS must be running AND you must be inside a mission.
REM    2. Fly whatever you want to capture.
REM    3. Close the "dcs-recorder" window to stop. The file is already on disk.
REM
REM  Output: tests\fixtures\recording\dcs-YYYYmmdd-HHMMSS.jsonl
REM ============================================================

setlocal
cd /d "%~dp0.."

echo.
echo ============================================================
echo   DCS telemetry recorder
echo ============================================================
echo   Output folder: tests\fixtures\recording\
echo.
echo   What is worth recording:
echo     - taxi / takeoff / climb      (slow changes, tests interpolation)
echo     - cruise, straight and level  (tests stability, no jitter)
echo     - hard maneuvering            (tests needle smoothing, G load)
echo     - switches and menus          (tests command throughput)
echo.
echo   Aim for 30-90 seconds each. Longer is not better.
echo.
echo   Press Ctrl+C or close the recorder window to stop.
echo ============================================================
echo.
pause

start "dcs-watchdog" cmd /c "python -u tools\usb-watchdog.py --interval 2"
timeout /t 1 >nul

echo Starting recorder...
python -u tools\beacon.py --port 8080 --ipv4-only --record tests\fixtures\recording\

echo.
echo Recorder stopped. Your file is in tests\fixtures\recording\
echo.
pause

@echo off
REM ============================================================
REM  DCS Peripheral - open inbound port for the bridge service
REM
REM  Why this is needed:
REM    This PC's Wi-Fi (SJTU) is classified as a "Public" network.
REM    Windows Firewall blocks inbound connections on Public by default,
REM    and the existing allow-rules only cover OTHER python.exe paths
REM    (python310, miniconda, trae, workbuddy\resources\vendor\python).
REM    The interpreter we actually run has no rule, so the phone's
REM    SYN is silently dropped -> it shows "timeout" instead of "refused".
REM
REM  How to run:
REM    Right-click this file -> "Run as administrator"
REM
REM  To undo later:
REM    netsh advfirewall firewall delete rule name="DCS Peripheral Bridge"
REM ============================================================

net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [!] Administrator privileges required.
    echo     Right-click this file and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo.
echo [*] Adding inbound rules...

netsh advfirewall firewall delete rule name="DCS Peripheral Bridge" >nul 2>&1

netsh advfirewall firewall add rule ^
    name="DCS Peripheral Bridge" ^
    dir=in action=allow protocol=TCP localport=8080,8443 ^
    profile=private,public

if errorlevel 1 (
    echo.
    echo [x] Failed to add rule.
    pause
    exit /b 1
)

echo.
echo [OK] Done. Inbound TCP 8080 and 8443 are now allowed on Private and Public.
echo.
echo Next: go back to the app and it should connect within a couple of seconds.
echo If it STILL times out, the campus Wi-Fi is doing client isolation,
echo which means you need Tailscale or a phone hotspot instead.
echo.
pause

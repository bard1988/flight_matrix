@echo off
rem Serve SkyMatrix to the corporate network from this workstation.
rem
rem   serve.cmd              start the server, reachable by colleagues
rem   serve.cmd /firewall    one-time: open the port (needs an ELEVATED prompt)
rem
rem This is a .cmd rather than a .ps1 on purpose: group policy sets AllSigned for
rem Windows PowerShell on this machine, so an unsigned .ps1 will not run there.
rem
rem One process only. Search progress is streamed from an in-memory registry, so a
rem second worker would answer some stream requests with "unknown search id".

setlocal
cd /d "%~dp0"

set PORT=8712
set RULE=SkyMatrix %PORT%

if /i "%~1"=="/firewall" goto :firewall

netsh advfirewall firewall show rule name="%RULE%" >nul 2>&1
if errorlevel 1 (
    echo [!] No inbound firewall rule for TCP %PORT% - colleagues will not be able to connect.
    echo [!] Once, in an ELEVATED command prompt:  "%~f0" /firewall
    echo.
)

echo Starting SkyMatrix on all interfaces, port %PORT%.
echo Callers must be on the corporate network or VPN, and this machine must stay awake.
echo There is no login: anyone who can reach this host can run searches.
echo Press Ctrl+C to stop.
echo.
py -3 run.py --host 0.0.0.0 --port %PORT% --no-open
goto :eof

:firewall
net session >nul 2>&1
if errorlevel 1 (
    echo This needs an elevated prompt. Right-click Command Prompt, "Run as administrator",
    echo then run:  "%~f0" /firewall
    exit /b 1
)
netsh advfirewall firewall show rule name="%RULE%" >nul 2>&1
if not errorlevel 1 (
    echo Firewall rule "%RULE%" already exists.
    exit /b 0
)
rem Domain profile only, so the port stays closed on home and public Wi-Fi.
netsh advfirewall firewall add rule name="%RULE%" dir=in action=allow protocol=TCP ^
    localport=%PORT% profile=domain
if errorlevel 1 (
    echo Failed to create the rule. Group policy may be blocking local firewall changes;
    echo in that case ask IT to allow inbound TCP %PORT% on this host.
    exit /b 1
)
echo Created firewall rule "%RULE%" ^(domain profile, inbound TCP %PORT%^).
exit /b 0

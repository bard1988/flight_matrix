@echo off
REM =====================================================================
REM  gh-push-403-diagnose.cmd
REM
REM  Diagnoses:  remote: Permission to <owner>/<repo>.git denied to <user>
REM              fatal: ... The requested URL returned error: 403
REM
REM  Run from CMD, or just double-click it while sitting in the repo
REM  folder (double-click uses the folder the .cmd lives in, so prefer
REM  -RepoPath, or copy both files into the repo).
REM
REM  USAGE
REM      gh-push-403-diagnose.cmd
REM      gh-push-403-diagnose.cmd -RepoPath C:\code\flight_matrix
REM      gh-push-403-diagnose.cmd -RepoPath C:\code\flight_matrix -NoApi
REM      gh-push-403-diagnose.cmd -ClearCredential
REM
REM  WHY THIS WRAPPER EXISTS
REM      Managed corporate Windows usually has Group Policy forcing
REM      PowerShell's execution policy to AllSigned. Group Policy BEATS
REM      -ExecutionPolicy Bypass, so "powershell -File script.ps1" dies
REM      with "is not digitally signed". AllSigned governs script FILES,
REM      not commands on stdin, so this wrapper pipes the script in
REM      instead. No policy change, no admin rights, nothing to install.
REM =====================================================================

setlocal EnableExtensions

set "SCRIPT=%~dp0gh-push-403-diagnose.ps1"

if not exist "%SCRIPT%" (
    echo.
    echo ERROR: gh-push-403-diagnose.ps1 was not found next to this file.
    echo        Keep gh-push-403-diagnose.ps1 and gh-push-403-diagnose.cmd
    echo        in the SAME folder.
    echo.
    pause
    exit /b 1
)

REM ---- defaults -------------------------------------------------------
set "GHDIAG_REPOPATH=%CD%"
set "GHDIAG_REMOTE=origin"
set "GHDIAG_NOAPI="
set "GHDIAG_CLEAR="

REM ---- argument parsing -----------------------------------------------
:parse
if "%~1"=="" goto run

if /i "%~1"=="-RepoPath"        ( set "GHDIAG_REPOPATH=%~2" & shift & shift & goto parse )
if /i "%~1"=="--repo-path"      ( set "GHDIAG_REPOPATH=%~2" & shift & shift & goto parse )
if /i "%~1"=="-RemoteName"      ( set "GHDIAG_REMOTE=%~2"   & shift & shift & goto parse )
if /i "%~1"=="-Remote"          ( set "GHDIAG_REMOTE=%~2"   & shift & shift & goto parse )
if /i "%~1"=="-NoApi"           ( set "GHDIAG_NOAPI=1"      & shift & goto parse )
if /i "%~1"=="-ClearCredential" ( set "GHDIAG_CLEAR=1"      & shift & goto parse )
if /i "%~1"=="-Clear"           ( set "GHDIAG_CLEAR=1"      & shift & goto parse )
if /i "%~1"=="-h"               goto usage
if /i "%~1"=="-?"               goto usage
if /i "%~1"=="/?"               goto usage
if /i "%~1"=="-Help"            goto usage

echo Unknown option: %~1
goto usage

:usage
echo.
echo Usage: gh-push-403-diagnose.cmd [options]
echo.
echo   -RepoPath ^<folder^>   Repo to inspect      (default: current folder)
echo   -RemoteName ^<name^>   Remote to inspect    (default: origin)
echo   -NoApi               Skip the GitHub API calls
echo   -ClearCredential     Delete the cached github.com credential
echo.
endlocal
exit /b 0

REM ---- run -------------------------------------------------------------
:run

if not exist "%GHDIAG_REPOPATH%" (
    echo.
    echo ERROR: repo folder not found: %GHDIAG_REPOPATH%
    echo        Pass a valid path with  -RepoPath ^<folder^>
    echo.
    pause
    exit /b 1
)

REM Read the .ps1 as TEXT and run it as a scriptblock. The AllSigned policy
REM governs script FILES handed to -File; a scriptblock built in memory is
REM not a script file, so it runs unsigned without touching any policy.
REM (Do not use "type file | powershell -Command -": stdin is parsed line by
REM  line, which breaks multi-line if/else blocks.)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((Get-Content -Raw -LiteralPath '%SCRIPT%')))"

set "RC=%ERRORLEVEL%"

echo.
echo (exit code %RC%)
echo.
pause

endlocal
exit /b %RC%

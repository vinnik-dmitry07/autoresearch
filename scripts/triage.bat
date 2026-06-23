@echo off
rem Fast experiment triage after editing strategy_heuristic.cpp
rem Usage:
rem   scripts\triage.bat              smoke + B4 quick + ladder quick (default)
rem   scripts\triage.bat smoke        gate 0 only (5k seeds vs B4)
rem   scripts\triage.bat b4           smoke + B4 quick
rem   scripts\triage.bat quick        smoke + B4 quick + ladder quick
rem   scripts\triage.bat full         all gates + 5M ladder full eval (no delta gate)
rem
rem Optional env vars:
rem   BEST_SEARCH=0.73239   print delta after ladder quick; suggest full if >= 0.006
rem   SKIP_BUILD=1          skip durak\build.bat fast
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set "STAGE=%~1"
if "%STAGE%"=="" set "STAGE=quick"

set "SIM=durak\build\simulate.exe"
set "LOG=durak\triage.log"
set "BUILD=durak\build.bat"
set "FULL_THRESH=0.006"

if not defined SKIP_BUILD (
    echo === rebuild (fast) ===
    call "%BUILD%" fast || exit /b 1
)

if not exist "%SIM%" (
    echo simulate.exe missing; run durak\build.bat first.
    exit /b 1
)

echo. > "%LOG%"
echo === triage stage=%STAGE% best_search=%BEST_SEARCH% === >> "%LOG%"

call :gate0 || exit /b 1
if /i "%STAGE%"=="smoke" goto :summary

call :gate1 || exit /b 1
if /i "%STAGE%"=="b4" goto :summary

call :gate2 || exit /b 1
if /i "%STAGE%"=="quick" goto :summary

if /i not "%STAGE%"=="full" (
    echo Unknown stage "%STAGE". Use smoke^|b4^|quick^|full
    exit /b 1
)

call :gate3 || exit /b 1
goto :summary

:summary
echo.
echo === triage summary (%STAGE%) ===
type "%LOG%"
echo.
echo Log: %LOG%
exit /b 0

:gate0
echo === Gate 0: smoke (5k seeds vs B4) ===
"%SIM%" --mode match --opponent B4 --seeds 5000 --batch 5000 >> "%LOG%" 2>&1
if errorlevel 1 (
    echo GATE 0 FAIL: simulate crashed
    type "%LOG%"
    exit /b 1
)
echo GATE 0 PASS
exit /b 0

:gate1
echo === Gate 1: B4 quick (100k seeds) ===
"%SIM%" --mode match --opponent B4 --eval quick --batch 50000 >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "$l=Get-Content '%LOG%' | Where-Object { $_ -match 'point_rate=' -and $_ -notmatch 'ladder' } | Select-Object -Last 1; if ($l -match 'point_rate=([0-9.]+)') { $matches[1] }"`) do set "G1_B4=%%a"
echo Gate 1 B4 point_rate=!G1_B4!
echo GATE 1 PASS
exit /b 0

:gate2
echo === Gate 2: ladder quick (100k seeds) ===
"%SIM%" --mode ladder --eval quick --batch 50000 >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "$l=Get-Content '%LOG%' | Where-Object { $_ -match '^search_score=' } | Select-Object -Last 1; if ($l -match 'search_score=([0-9.]+)') { $matches[1] }"`) do set "G2_SEARCH=%%a"
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "$l=Get-Content '%LOG%' | Where-Object { $_ -match '^B2 vs B4' } | Select-Object -Last 1; if ($l -match 'point_rate=([0-9.]+)') { $matches[1] }"`) do set "G2_B4=%%a"
echo Gate 2 search_score=!G2_SEARCH!  B4 point_rate=!G2_B4!
if not defined BEST_SEARCH goto :gate2_done
if not defined G2_SEARCH goto :gate2_done
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_SEARCH!'-[double]'%BEST_SEARCH%'"`) do set "DELTA=%%d"
echo Delta search_score vs best !BEST_SEARCH!: !DELTA!
powershell -NoProfile -Command "if ([double]'!DELTA!' -ge %FULL_THRESH%) { Write-Host 'Recommend full eval: delta >= %FULL_THRESH%' } else { Write-Host 'Skip full eval: delta below %FULL_THRESH%' }"
:gate2_done
echo GATE 2 PASS
exit /b 0

:gate3
echo === Gate 3: ladder full (5M seeds) ===
"%SIM%" --mode ladder --eval full --batch 500000 >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1
echo GATE 3 DONE — read search_score / keep rule from log above
exit /b 0

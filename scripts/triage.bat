@echo off
rem Fast experiment triage after editing strategy_heuristic.cpp
rem Usage:
rem   scripts\triage.bat              smoke + parallel ladder quick (default)
rem   scripts\triage.bat smoke        gate 0 only (5k seeds vs B4)
rem   scripts\triage.bat b4           smoke + B4 quick only (~1.5s)
rem   scripts\triage.bat quick        smoke + parallel ladder quick (~6s)
rem   scripts\triage.bat medium       smoke + parallel ladder 500k (~12s)
rem   scripts\triage.bat dual         smoke + two quick ladders seed 0/1 (~12s)
rem   scripts\triage.bat full         quick + delta gate + parallel full (~1.7m)
rem
rem Optional env vars:
rem   BEST_SEARCH=0.77341   delta vs best for search_score
rem   BEST_B4=0.61206       early exit B1/B0; B4-first full gate
rem   FORCE_FULL=1          run gate 3 even when delta below threshold
rem   SKIP_BUILD=1          skip durak\build.bat fast
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

set "STAGE=%~1"
if "%STAGE%"=="" set "STAGE=quick"

set "SIM=durak\build\simulate.exe"
set "LOG=durak\triage.log"
set "BUILD=durak\build.bat"
set "LADDER_PS=scripts\triage_ladder.ps1"
set "DISCARD_THRESH=0.003"
set "FULL_SEARCH_THRESH=0.006"
set "FULL_B4_THRESH=0.005"

if not defined SKIP_BUILD (
    echo === rebuild (fast) ===
    call "%BUILD%" fast || exit /b 1
)

if not exist "%SIM%" (
    echo simulate.exe missing; run durak\build.bat first.
    exit /b 1
)

echo. > "%LOG%"
echo === triage stage=%STAGE% best_search=%BEST_SEARCH% best_b4=%BEST_B4% === >> "%LOG%"

call :gate0 || exit /b 1
if /i "%STAGE%"=="smoke" goto :summary

if /i "%STAGE%"=="b4" (
    call :gate1 || exit /b 1
    goto :summary
)

if /i "%STAGE%"=="medium" (
    set "G2_EVAL=medium"
    set "G2_SEED_BASE=0"
    call :gate2 || exit /b 1
    goto :summary
)

if /i "%STAGE%"=="dual" (
    call :gate_dual || exit /b 1
    goto :summary
)

set "G2_EVAL=quick"
set "G2_SEED_BASE=0"
call :gate2 || exit /b 1
if /i "%STAGE%"=="quick" goto :summary

if /i not "%STAGE%"=="full" (
    echo Unknown stage "%STAGE%". Use smoke^|b4^|quick^|medium^|dual^|full
    exit /b 1
)

call :gate3_check || exit /b 1
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
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "$l=Get-Content '%LOG%' | Where-Object { $_ -match 'point_rate=' } | Select-Object -Last 1; if ($l -match 'point_rate=([0-9.]+)') { $matches[1] }"`) do set "G1_B4=%%a"
echo Gate 1 B4 point_rate=!G1_B4!
echo GATE 1 PASS
exit /b 0

:gate2
if not defined G2_EVAL set "G2_EVAL=quick"
if not defined G2_SEED_BASE set "G2_SEED_BASE=0"
echo === Gate 2: parallel ladder !G2_EVAL! seed_base=!G2_SEED_BASE! ===
set "G2_PS_ARGS=-Eval !G2_EVAL! -LogPath %LOG% -SeedBase !G2_SEED_BASE!"
if defined BEST_B4 set "G2_PS_ARGS=!G2_PS_ARGS! -BestB4 %BEST_B4%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%LADDER_PS%" !G2_PS_ARGS!
if errorlevel 1 exit /b 1
call :read_ladder_scores G2 !G2_EVAL! !G2_SEED_BASE! || exit /b 1
echo Gate 2 search_score=!G2_SEARCH!  B4 point_rate=!G2_B4!
call :print_delta
echo GATE 2 PASS
exit /b 0

:gate_dual
echo === Gate dual: parallel ladder quick seed 0 then seed 1 ===
set "G2_EVAL=quick"
set "G2_SEED_BASE=0"
call :gate2 || exit /b 1
set "G2_SEARCH_0=!G2_SEARCH!"
set "G2_B4_0=!G2_B4!"
set "G2_SEED_BASE=1"
call :gate2 || exit /b 1
set "G2_SEARCH_1=!G2_SEARCH!"
set "G2_B4_1=!G2_B4!"
call :print_dual_verdict
echo GATE DUAL PASS
exit /b 0

:gate3_check
if not defined G2_SEARCH (
    set "G2_EVAL=quick"
    set "G2_SEED_BASE=0"
    echo Gate 3: re-running quick ladder for delta check...
    call :gate2 || exit /b 1
)
if not defined G2_SEARCH (
    echo ERROR: gate 3 needs search_score from gate 2
    exit /b 1
)
call :compute_deltas
if defined FORCE_FULL goto :gate3_run
if not defined BEST_SEARCH goto :gate3_run

powershell -NoProfile -Command "if ([double]'!DELTA_SEARCH!' -ge %FULL_SEARCH_THRESH%) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto :gate3_run

if defined DELTA_B4 (
    powershell -NoProfile -Command "if ([double]'!DELTA_B4!' -ge %FULL_B4_THRESH%) { exit 0 } else { exit 1 }"
    if not errorlevel 1 (
        echo Gate 3: B4-first trigger delta_B4=!DELTA_B4! ^>= %FULL_B4_THRESH%
        echo Gate 3: B4-first trigger delta_B4=!DELTA_B4! >> "%LOG%"
        goto :gate3_run
    )
)

powershell -NoProfile -Command "$ds=[double]'!DELTA_SEARCH!'; $db=if('!DELTA_B4!' -eq ''){0}else{[double]'!DELTA_B4!'}; if ($ds -lt %DISCARD_THRESH% -and $db -lt %DISCARD_THRESH%) { exit 2 } elseif ($ds -ge %DISCARD_THRESH% -or $db -ge %DISCARD_THRESH%) { exit 1 } else { exit 0 }"
set "G3_HINT=!errorlevel!"
if "!G3_HINT!"=="2" (
    echo SKIP Gate 3: clear discard zone ^(delta_search=!DELTA_SEARCH! delta_B4=!DELTA_B4!^)
    echo SKIP Gate 3: clear discard zone >> "%LOG%"
    exit /b 0
)
if "!G3_HINT!"=="1" (
    echo SKIP Gate 3: maybe zone — try scripts\triage.bat medium or dual
    echo SKIP Gate 3: maybe zone delta_search=!DELTA_SEARCH! delta_B4=!DELTA_B4! >> "%LOG%"
    exit /b 0
)
echo SKIP Gate 3: delta !DELTA_SEARCH! below %FULL_SEARCH_THRESH% ^(set FORCE_FULL=1 to override^)
echo SKIP Gate 3: delta !DELTA_SEARCH! below %FULL_SEARCH_THRESH% >> "%LOG%"
exit /b 0

:gate3_run
call :gate3 || exit /b 1
exit /b 0

:gate3
echo === Gate 3: parallel ladder full (5M seeds) ===
set "G3_PS_ARGS=-Eval full -LogPath %LOG% -SeedBase 0"
if defined BEST_B4 set "G3_PS_ARGS=!G3_PS_ARGS! -BestB4 %BEST_B4%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%LADDER_PS%" !G3_PS_ARGS!
if errorlevel 1 exit /b 1
call :read_ladder_scores G3 full 0 || exit /b 1
echo Gate 3 search_score=!G3_SEARCH!  B4 point_rate=!G3_B4!
echo GATE 3 DONE — apply keep rule vs BEST_SEARCH=%BEST_SEARCH%
exit /b 0

:read_ladder_scores
set "PREFIX=%~1"
set "EVAL_TAG=%~2"
set "SEED_TAG=%~3"
if not defined EVAL_TAG set "EVAL_TAG=quick"
if not defined SEED_TAG set "SEED_TAG=0"
set "SCORE_FILE=durak\triage_parts\search_score_%EVAL_TAG%_%SEED_TAG%.txt"
if exist "!SCORE_FILE!" (
    set /p %PREFIX%_SEARCH=<"!SCORE_FILE!"
)
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "$lines=Get-Content '%LOG%'; $tag='%EVAL_TAG% seed_base=%SEED_TAG%'; $i=0..($lines.Count-1) | Where-Object { $lines[$_] -like '*ladder results*' -and $lines[$_] -like ('*' + $tag + '*') } | Select-Object -Last 1; if ($null -eq $i) { exit 1 }; $block=$lines[$i..([Math]::Min($i+8,$lines.Count-1))]; foreach ($l in $block) { if ($l -like 'B2 vs B4*' -and $l -match 'point_rate=([0-9.]+)') { $matches[1]; break } }"`) do set "%PREFIX%_B4=%%a"
if not defined %PREFIX%_SEARCH (
    echo ERROR: could not read search_score from !SCORE_FILE!
    exit /b 1
)
exit /b 0

:compute_deltas
set "DELTA_SEARCH="
set "DELTA_B4="
if not defined BEST_SEARCH goto :eof
if defined G2_SEARCH (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_SEARCH!'-[double]'%BEST_SEARCH%'"`) do set "DELTA_SEARCH=%%d"
)
if defined BEST_B4 if defined G2_B4 (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_B4!'-[double]'%BEST_B4%'"`) do set "DELTA_B4=%%d"
)
exit /b 0

:print_delta
call :compute_deltas
if not defined DELTA_SEARCH goto :eof
echo Delta search_score vs best !BEST_SEARCH!: !DELTA_SEARCH!
if defined DELTA_B4 echo Delta B4 point_rate vs best !BEST_B4!: !DELTA_B4!
powershell -NoProfile -Command "$ds=[double]'!DELTA_SEARCH!'; $db=if('!DELTA_B4!' -eq ''){0}else{[double]'!DELTA_B4!'}; if ($ds -ge %FULL_SEARCH_THRESH% -or $db -ge %FULL_B4_THRESH%) { Write-Host 'Recommend full eval: search or B4 delta above threshold' } elseif ($ds -lt %DISCARD_THRESH% -and $db -lt %DISCARD_THRESH%) { Write-Host 'Recommend discard: both deltas below %DISCARD_THRESH%' } else { Write-Host 'Maybe zone: triage.bat medium or triage.bat dual before full' }"
goto :eof

:print_dual_verdict
set "DELTA_SEARCH_0="
set "DELTA_SEARCH_1="
set "DELTA_B4_0="
set "DELTA_B4_1="
if defined BEST_SEARCH (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_SEARCH_0!'-[double]'%BEST_SEARCH%'"`) do set "DELTA_SEARCH_0=%%d"
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_SEARCH_1!'-[double]'%BEST_SEARCH%'"`) do set "DELTA_SEARCH_1=%%d"
)
if defined BEST_B4 (
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_B4_0!'-[double]'%BEST_B4%'"`) do set "DELTA_B4_0=%%d"
    for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[double]'!G2_B4_1!'-[double]'%BEST_B4%'"`) do set "DELTA_B4_1=%%d"
)
echo Dual seed 0: search=!G2_SEARCH_0! delta_search=!DELTA_SEARCH_0! B4=!G2_B4_0! delta_B4=!DELTA_B4_0!
echo Dual seed 1: search=!G2_SEARCH_1! delta_search=!DELTA_SEARCH_1! B4=!G2_B4_1! delta_B4=!DELTA_B4_1!
powershell -NoProfile -Command "$ds0=[double]'!DELTA_SEARCH_0!'; $ds1=[double]'!DELTA_SEARCH_1!'; $db0=[double]'!DELTA_B4_0!'; $db1=[double]'!DELTA_B4_1!'; $fullSearch=($ds0 -ge %FULL_SEARCH_THRESH% -and $ds1 -ge %FULL_SEARCH_THRESH%); $fullB4=($db0 -ge %FULL_B4_THRESH% -and $db1 -ge %FULL_B4_THRESH%); if ($fullSearch -or $fullB4) { Write-Host 'Dual agree: recommend triage.bat full or FORCE_FULL=1' } else { Write-Host 'Dual disagree or below threshold: try triage.bat medium or discard' }"
goto :eof

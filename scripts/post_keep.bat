@echo off
rem Post-keep protocol: tests, optional ablation, optional analysis refresh.
rem Usage: scripts\post_keep.bat
rem   SKIP_ABLATE=1     skip memory ablation (~2 min; use when B3 vs B2 is known 0.5)
rem   SKIP_ANALYSIS=1   skip run_analysis.bat (~15s)
setlocal
cd /d "%~dp0\.."

echo === post-keep: tests ===
call durak\build.bat test || exit /b 1

if not defined SKIP_ABLATE (
    echo === post-keep: memory ablation ===
    durak\build\simulate.exe --mode ablate --eval full
    if errorlevel 1 exit /b 1
) else (
    echo SKIP ablation ^(SKIP_ABLATE=1^)
)

if not defined SKIP_ANALYSIS (
    echo === post-keep: analysis ===
    call scripts\run_analysis.bat || exit /b 1
) else (
    echo SKIP analysis ^(SKIP_ANALYSIS=1^)
)

echo post-keep done

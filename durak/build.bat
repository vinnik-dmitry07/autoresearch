@echo off
rem Configure + build the Durak engine with the Visual Studio toolchain.
rem Usage: build.bat            (configure + build, Release)
rem        build.bat fast       (incremental build only; skip configure if build/ exists)
rem        build.bat test       (configure + build + run ctest)
rem        build.bat fast test  (incremental build + ctest)
setlocal

set "VS=D:\Programs\Microsoft_Visual_Studio"
set "VCVARS=%VS%\VC\Auxiliary\Build\vcvars64.bat"
set "CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
set "SRC=%~dp0"

set "MODE=%~1"
set "SUB=%~2"
if "%MODE%"=="fast" (
    if "%SUB%"=="test" set "RUN_TEST=1"
) else if "%MODE%"=="test" (
    set "RUN_TEST=1"
) else (
    set "MODE=configure"
)

call "%VCVARS%" >nul || exit /b 1

if "%MODE%"=="fast" (
    if not exist "%SRC%build\build.ninja" (
        echo build.bat fast: no build tree; running full configure...
        "%CMAKE%" -S "%SRC%." -B "%SRC%build" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release || exit /b 1
    )
) else (
    "%CMAKE%" -S "%SRC%." -B "%SRC%build" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release || exit /b 1
)

"%CMAKE%" --build "%SRC%build" || exit /b 1

if defined RUN_TEST (
    "%CMAKE%" --build "%SRC%build" --target engine_tests simulation_tests || exit /b 1
    pushd "%SRC%build"
    ctest --output-on-failure
    set "RC=%ERRORLEVEL%"
    popd
    exit /b %RC%
)
exit /b 0

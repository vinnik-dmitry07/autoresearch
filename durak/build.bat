@echo off
rem Configure + build the Durak engine with the Visual Studio toolchain.
rem Usage: build.bat            (configure + build, Release)
rem        build.bat test       (configure + build + run ctest)
setlocal

set "VS=D:\Programs\Microsoft_Visual_Studio"
set "VCVARS=%VS%\VC\Auxiliary\Build\vcvars64.bat"
set "CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
set "SRC=%~dp0"

call "%VCVARS%" >nul || exit /b 1

"%CMAKE%" -S "%SRC%." -B "%SRC%build" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release || exit /b 1
"%CMAKE%" --build "%SRC%build" || exit /b 1

if "%~1"=="test" (
    "%CMAKE%" --build "%SRC%build" --target engine_tests simulation_tests || exit /b 1
    pushd "%SRC%build"
    ctest --output-on-failure
    set "RC=%ERRORLEVEL%"
    popd
    exit /b %RC%
)
exit /b 0

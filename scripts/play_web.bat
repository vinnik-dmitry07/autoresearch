@echo off
rem Start the Durak web UI (B2 agent). Open http://localhost:8080
setlocal
set "EXE=%~dp0..\durak\build\web_server.exe"

rem Build the web_server target (incremental). Fail loudly if it cannot be produced
rem -- the most common cause is an instance already running and locking the .exe.
echo Building web_server...
call "%~dp0..\durak\build.bat" web
if errorlevel 1 (
    echo.
    echo ERROR: failed to build web_server.exe.
    echo   If the web UI is already running, stop it first:
    echo       taskkill /IM web_server.exe /F
    echo   then re-run this script. To build everything:  durak\build.bat
    exit /b 1
)
if not exist "%EXE%" (
    echo.
    echo ERROR: web_server.exe not found at "%EXE%" after build.
    echo   Build it manually with: durak\build.bat
    exit /b 1
)

echo.
echo Durak web UI: http://localhost:8080
echo Press Ctrl+C to stop.
echo.
"%EXE%" %*

@echo off
rem Start the Durak web UI (B2 agent). Open http://localhost:8080
setlocal
set "EXE=%~dp0..\durak\build\web_server.exe"
if not exist "%EXE%" (
    echo Building web_server...
    call "%~dp0..\durak\build.bat" fast || exit /b 1
)
echo.
echo Durak web UI: http://localhost:8080
echo Press Ctrl+C to stop.
echo.
"%EXE%" %*

@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv-windows\Scripts\python.exe" goto run
echo Creating Renmon environment. Python 3.10 or newer is required.
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv-windows
    goto install
)
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto python_missing
python -m venv .venv-windows
:install
if not exist ".venv-windows\Scripts\python.exe" goto failed
".venv-windows\Scripts\python.exe" -m pip install -e ".[desktop]"
if errorlevel 1 goto failed
:run
".venv-windows\Scripts\python.exe" -c "import serial, renmon, webview" >nul 2>&1
if errorlevel 1 goto install
if not exist "renmon\ui.bundle.js" (
    where npm.cmd >nul 2>&1
    if errorlevel 1 (
        echo Install Node.js to build the UI from source.
        goto failed
    )
    call npm ci
    if errorlevel 1 goto failed
    call npm run build
    if errorlevel 1 goto failed
)
echo Starting Renmon desktop. No HTTP server is used.
".venv-windows\Scripts\python.exe" -m renmon.desktop
if errorlevel 1 goto failed
exit /b 0
:python_missing
echo Install Python 3.10 or newer from python.org, including the Python launcher.
echo Then run this file again.
pause
exit /b 1
:failed
echo Renmon could not start. See the error above.
pause
exit /b 1

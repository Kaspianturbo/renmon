@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
py -3 -m venv .venv-build-windows
if errorlevel 1 goto failed
".venv-build-windows\Scripts\python.exe" -m pip install ".[desktop,build]"
if errorlevel 1 goto failed
call npm ci
if errorlevel 1 goto failed
".venv-build-windows\Scripts\python.exe" packaging\build_portable.py
if errorlevel 1 goto failed
echo Portable files are in dist. Copy the entire Renmon folder to the target PC.
pause
exit /b 0
:failed
echo Build failed. Python 3.10+, Node.js and internet access are required on this build PC.
pause
exit /b 1

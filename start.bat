@echo off
cd /d "%~dp0"
echo ==============================================
echo   Starting Download Manager (Client + Server)
echo ==============================================

echo [1/2] Starting Python Daemon in the background...
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" daemon.py
) else (
    start "" pythonw daemon.py
)

echo [2/2] Starting C# WinUI 3 Frontend...
start "" "DownloadManagerUI\bin\Debug\net8.0-windows10.0.26100.0\win-x64\DownloadManagerUI.exe"

echo.
echo Launching complete.

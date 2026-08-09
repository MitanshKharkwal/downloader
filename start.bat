@echo off
cd /d "%~dp0"
echo ==============================================
echo   Starting Download Manager (Client + Server)
echo ==============================================

echo [1/2] Starting Python Daemon in the background...
start /B python daemon.py

echo [2/2] Starting C# WinUI 3 Frontend...
cd DownloadManagerUI
dotnet run
cd ..

echo.
echo Closing frontend...

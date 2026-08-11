@echo off
cd /d "%~dp0"
echo ==============================================
echo   Starting Unified Download Manager
echo ==============================================

echo [1/2] Starting Python Daemon in the background...
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" daemon.py
) else (
    start "" pythonw daemon.py
)

echo [2/2] Starting Unified Flutter App...
cd flutter_ui
flutter run -d windows
cd ..

echo.
echo Launching complete.

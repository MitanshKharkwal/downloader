@echo off
cd /d "C:\Users\mitan\Downloads\download_manager_1\download_manager\native_host\.."
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -u "C:\Users\mitan\Downloads\download_manager_1\download_manager\native_host\host.py"
) else (
    python -u "C:\Users\mitan\Downloads\download_manager_1\download_manager\native_host\host.py"
)

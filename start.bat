@echo off
setlocal
cd /d "%~dp0"
echo Starting Fetchly...

rem Replace an idle copy of our service, but never interrupt an active download.
powershell -NoProfile -Command "$listener=Get-NetTCPConnection -LocalPort 47821 -State Listen -ErrorAction SilentlyContinue; if (-not $listener) { exit 0 }; $tokenPath=Join-Path $env:USERPROFILE '.download_manager\ipc_token.txt'; if (-not (Test-Path -LiteralPath $tokenPath)) { exit 1 }; try { $token=(Get-Content -LiteralPath $tokenPath -Raw).Trim(); $headers=@{'X-Auth-Token'=$token}; $listBody=@{method='list_tasks';args=@{}} | ConvertTo-Json -Compress; $list=Invoke-RestMethod -Uri 'http://127.0.0.1:47821/rpc' -Method Post -ContentType 'application/json' -Headers $headers -Body $listBody -TimeoutSec 4; if ($list.tasks | Where-Object { $_.status -in @('DOWNLOADING','CONNECTING') }) { exit 2 }; $stopBody=@{method='shutdown';args=@{}} | ConvertTo-Json -Compress; Invoke-RestMethod -Uri 'http://127.0.0.1:47821/rpc' -Method Post -ContentType 'application/json' -Headers $headers -Body $stopBody -TimeoutSec 4 | Out-Null; for ($i=0; $i -lt 40; $i++) { if (-not (Get-NetTCPConnection -LocalPort 47821 -State Listen -ErrorAction SilentlyContinue)) { exit 0 }; Start-Sleep -Milliseconds 100 }; exit 1 } catch { exit 1 }"
if errorlevel 2 (
    echo A download is currently active. Finish or pause it before restarting Fetchly.
    pause
    exit /b 1
)
if errorlevel 1 (
    echo Port 47821 is occupied and the existing service could not be restarted safely.
    pause
    exit /b 1
)

echo Building the Windows app...
pushd flutter_ui
call flutter build windows --release
if errorlevel 1 (
    popd
    pause
    exit /b 1
)
popd

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" daemon.py
) else (
    start "" pythonw daemon.py
)

rem Wait for the service so the UI does not open into a false disconnected state.
powershell -NoProfile -Command "$ready=$false; for ($i=0; $i -lt 50; $i++) { try { $client=[Net.Sockets.TcpClient]::new('127.0.0.1',47821); $client.Dispose(); $ready=$true; break } catch { Start-Sleep -Milliseconds 100 } }; if (-not $ready) { exit 1 }"
if errorlevel 1 (
    echo The download service did not start. See %USERPROFILE%\.download_manager\daemon.log for details.
    pause
    exit /b 1
)

start "" "flutter_ui\build\windows\x64\runner\Release\flutter_ui.exe"
exit /b 0

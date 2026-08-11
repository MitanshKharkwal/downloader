# Download Manager – Mandatory IPC Contract Rules

When modifying either the Python backend (`core/`, `daemon.py`) or the C# WinUI frontend (`DownloadManagerUI/`), you **MUST** follow these rules to prevent deserialization failures and data-loss bugs between the two sides.

## Rule 1: Status values MUST be UPPERCASE strings

The Python daemon sends status values via `task.status.value` which returns **lowercase** enum strings (`"queued"`, `"downloading"`, etc.). The C# UI compares statuses against **UPPERCASE** strings (`"COMPLETED"`, `"DOWNLOADING"`, `"PAUSED"`, etc.).

- In `core/ipc_server.py`, always use `.upper()` when serializing status:
  ```python
  "status": task.status.value.upper(),
  ```
- In the C# UI (`Models.cs`, `DownloadsPage.xaml.cs`), always compare against uppercase:
  ```csharp
  if (task.Status == "COMPLETED") ...
  ```
- **Never** change one side's casing convention without updating the other.

## Rule 2: Priority MUST be serialized as an integer

The Python `Priority` enum is `int`-based (`LOW=0`, `NORMAL=1`, `HIGH=2`). The C# model's `Priority` property is `int`.

- In `core/ipc_server.py`, always send `task.priority.value` (which produces an `int`).
- In `DownloadManagerUI/Models.cs`, the `Priority` property must be declared as `int`, **not** `string`.
- **Never** change Priority to a string on either side without updating the other.

## Rule 3: All fields used by the C# UI MUST be present in the RPC response

The `list_tasks` RPC handler in `core/ipc_server.py` must include **every** field that the C# `DownloadTask` model declares with a `[JsonPropertyName]` attribute. Missing fields cause silent failures (empty task list, broken filters).

Current required fields:
```
id, source, status, priority, downloaded_bytes, total_bytes,
speed_bps, file_path, error, category, created_at, description
```

- When adding a new `[JsonPropertyName]` field in `Models.cs`, you **MUST** also add the corresponding key to the `list_tasks` handler in `ipc_server.py`.
- When removing a field from the Python response, you **MUST** remove or make optional the corresponding C# property.

## Rule 4: Type matching between Python JSON and C# deserialization

Every field sent by the Python daemon must match the expected C# type **exactly**. A mismatch (e.g., Python sends `int` but C# expects `string`) causes `System.Text.Json.JsonException` and the **entire task list silently fails to load**.

| Python type | C# type | Examples |
|-------------|---------|----------|
| `str` | `string` | id, source, status, file_path, error, category, description |
| `int` | `long` | downloaded_bytes, total_bytes |
| `int` (enum .value) | `int` | priority |
| `float` | `double` | speed_bps, created_at |

- Before changing any field's type on either side, check and update the other side.

## Rule 5: Test the IPC contract after any model change

After modifying either `core/ipc_server.py` (list_tasks handler) or `DownloadManagerUI/Models.cs`, verify the contract by:

1. Starting the daemon: `pythonw daemon.py`
2. Querying the RPC endpoint and checking the JSON shape:
   ```powershell
   $token = Get-Content ~/.download_manager/ipc_token.txt
   $body = '{"method":"list_tasks","args":{}}'
   Invoke-RestMethod -Uri "http://127.0.0.1:47821/rpc" -Method Post -Headers @{"X-Auth-Token"=$token; "Content-Type"="application/json"} -Body $body | ConvertTo-Json -Depth 3
   ```
3. Confirming every field name, type, and casing matches what `Models.cs` expects.

## Rule 6: The `start.bat` script must NOT use `dotnet run`

Using `dotnet run` ties the app process to the console. Closing the console kills the app (including the system tray icon). Instead:

```batch
dotnet build -c Debug
start "" "bin\Debug\net8.0-windows10.0.26100.0\win-x64\DownloadManagerUI.exe"
```

This compiles latest changes AND launches the app as a fully detached process.

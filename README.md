# downloader

An IDM-style download manager: multi-connection resumable HTTP downloads, magnet/torrent support, YouTube/video downloads via yt-dlp, a Flutter desktop app, and a Chrome extension that captures downloads and magnet links straight from the browser.

**Status:** active personal project, in development. The core engine and IPC layer are solid and tested; the Flutter UI and browser extension work but haven't been packaged for easy install yet — see [Setup](#setup) below for the current (manual, developer-oriented) way to run it.

<!-- Add a screenshot or short GIF of the Flutter UI here before sharing this repo widely — it's the single best thing you can add. -->

## Features

- Segmented, resumable HTTP downloads (multi-connection, auto-retry, resume across app restarts)
- Torrent/magnet downloads via libtorrent
- Video downloads via yt-dlp
- Auto-categorization by file type, auto-extraction of archives
- Global bandwidth caps with time-of-day scheduling, task priority levels
- Chrome extension: captures download links and magnet clicks and forwards them to the desktop app
- Flutter UI with a monochrome Material 3 design

## Architecture

```
Chrome extension (background.js)
    -- chrome.runtime.sendNativeMessage -->
native_host/host.py (spawned per-message by Chrome)
    -- HTTP POST /add, localhost only, token-authed -->
DownloadManager daemon (Python, core/ipc_server.py)
    -- in-process call -->
core.DownloadManager (core/manager.py)

Flutter UI (flutter_ui/)
    -- JSON-RPC over HTTP, POST /rpc -->
DownloadManager daemon (same process as above)
```

The daemon is a single headless Python process (`daemon.py`) that owns all download state. Two clients talk to it:
- The **browser extension**, via the native messaging host, using a legacy `POST /add` endpoint (this predates the RPC layer and is kept because it's the only way Chrome's native messaging can reach a local process).
- The **Flutter UI**, via a `POST /rpc` JSON method-dispatch endpoint (`list_tasks`, `pause`, `resume`, `cancel`, `retry`, `set_priority`, `clear_finished`, `add_video_task`, `get_config`, `set_config`, `shutdown`).

Both endpoints are localhost-only and token-authenticated.

## Layout

```
core/               engine: DownloadManager, HTTP/torrent/video backends, IPC server
daemon.py           entry point that starts the engine + IPC server
flutter_ui/         Flutter desktop app (current primary frontend)
browser_extension/  Chrome extension (Manifest V3): capture + interception
native_host/        bridges the extension to the running daemon
tests/              engine + IPC integration tests (pytest)
DownloadManagerUI_old/  legacy C# WinUI3 frontend, superseded by flutter_ui/, kept for reference only
```

## Setup

```
pip install -r requirements.txt
```

### 1. Start the daemon

```
python daemon.py
```

Downloads land in `~/.download_manager/downloads`. First run creates `~/.download_manager/ipc_token.txt` — other clients need this file to exist before they can authenticate to the daemon.

### 2. Start the Flutter UI

```
cd flutter_ui
flutter pub get
flutter run -d windows   # or macos / linux, depending on your platform
```

### 3. Browser extension (optional)

In Chrome: `chrome://extensions` → enable Developer mode → "Load unpacked" → select `browser_extension/`. Note the extension ID Chrome assigns it.

### 4. Native messaging host (optional, needed for the browser extension)

```
cd native_host
python register_native_host.py --extension-id <the ID from step 3>
```

On Windows this writes `run_host.bat` + `native_host_manifest.json` next to `host.py` and registers the manifest under `HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts`. On Mac/Linux, copy the generated manifest into Chrome's `NativeMessagingHosts` directory for your platform instead (see [Chrome's native messaging docs](https://developer.chrome.com/docs/apps/nativeMessaging/)).

## Testing

```
pytest tests/
```

## A note on intended use

This tool can download torrents and video from third-party sites via yt-dlp. It's built the same way any general-purpose download manager is — it doesn't target or circumvent any specific service — but you're responsible for using it in line with the terms of service of whatever site you point it at, and with content you have the rights to download. It's intended for personal backups, your own content, and public-domain or freely licensed material.

## License

MIT — see [LICENSE](LICENSE).

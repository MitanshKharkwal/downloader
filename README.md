# Downloader

A desktop download manager with a polished Flutter UI, a Python engine, and a Chrome extension — think IDM, but open-source and cross-platform.

## Features

| Capability | Detail |
|---|---|
| **Multi-connection HTTP** | Segmented, parallel, resumable downloads with auto-retry |
| **Torrent / Magnet** | Full torrent support via libtorrent |
| **Video downloads** | YouTube and 1000+ sites via yt-dlp |
| **Smart organisation** | Auto-categorisation by file type, auto-extraction of archives |
| **Bandwidth control** | Global cap, time-of-day scheduling, per-task priority |
| **Browser integration** | Chrome extension captures download links and magnet clicks |
| **Flutter UI** | Glass-skin desktop app — dark, animated, responsive |

## Architecture

```
Chrome extension  →  native_host/host.py  →  POST /add
                                                    ↓
Flutter UI        →  POST /rpc (JSON-RPC)  →  daemon.py (Python)
                                                    ↓
                                             core/manager.py
```

The daemon is a single headless Python process that owns all download state. Both clients (browser extension and Flutter UI) communicate over localhost-only, token-authenticated HTTP.

## Quickstart

### 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2 — Start the daemon

```bash
python daemon.py
```

Downloads land in `~/.download_manager/downloads/`. An auth token is created at `~/.download_manager/ipc_token.txt` on first run.

### 3 — Start the Flutter UI

```bash
cd flutter_ui
flutter pub get
flutter run -d windows    # or macos / linux
```

### 4 — Browser extension *(optional)*

1. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select `browser_extension/`.
2. Note the extension ID Chrome assigns.

```bash
cd native_host
python register_native_host.py --extension-id <ID from step 1>
```

## Testing

```bash
# Python engine tests
pytest tests/

# Flutter widget tests
cd flutter_ui && flutter test
```

## Project layout

```
core/                   Python engine (HTTP, torrent, video backends, IPC server)
daemon.py               Entry point — starts engine + IPC
flutter_ui/             Flutter desktop app
  lib/
    models/             Data types (DownloadTask, enums)
    services/           RPC client, polling service
    screens/            HomeScreen
    widgets/            TaskCard, Sidebar, AddUrlDialog, …
    theme/              AppColors, AppRadius, AppTheme (General Sans typography)
  assets/fonts/         Bundled General Sans typeface
browser_extension/      Chrome MV3 extension
native_host/            Bridges extension → daemon
tests/                  pytest integration suite
```

## Tech stack

- **Engine:** Python 3, aiohttp, libtorrent, yt-dlp, requests
- **UI:** Flutter (Windows / macOS / Linux), google_fonts, phosphor_icons, fl_chart
- **Typography:** General Sans (Fontshare)
- **Extension:** Chrome Manifest V3

## License

MIT — see [LICENSE](LICENSE).

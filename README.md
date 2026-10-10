# Downloader

A desktop download manager with a polished Flutter UI, a Python engine, and a Chrome extension — think IDM, but open-source, with a Windows desktop build.

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

Downloads land in `~/Downloads/`. An auth token is created at `~/.download_manager/ipc_token.txt` on first run.

### 3 — Start the Flutter UI

```bash
cd flutter_ui
flutter pub get
flutter run -d windows
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
# Python engine and native-host tests
pytest

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

- **Engine:** Python 3, libtorrent, yt-dlp, requests
- **UI:** Flutter (Windows), google_fonts, phosphor_icons, fl_chart
- **Typography:** General Sans (Fontshare)
- **Extension:** Chrome Manifest V3

## License

MIT — see [LICENSE](LICENSE).

## Reliability and local verification

History and download settings are stored in `~/.download_manager/state.json`, independently of the download folder. On first startup after upgrading, the daemon copies a legacy `.dm_state.json` from the configured download folder when present. Keep a backup of an older folder's state file if you changed directories before upgrading.

New torrents use a private directory named after the task ID. Legacy torrents retain their original location; offline deletion deliberately leaves their shared directory intact. Invalid HTTP range responses fail visibly instead of publishing potentially corrupted files. Servers without resource validators may require a fresh download after pausing.

The bandwidth setting is a payload-rate cap: HTTP and video share a bucket, with a separate portion assigned to libtorrent while both kinds are active. Low-priority tasks additionally use a live 1 MB/s background-mode cap; normal and high priority remain governed by the global limit. Network protocol overhead and short buffering bursts are outside those caps. Video mode currently offers combined video formats; separate high-resolution audio/video merging requires additional FFmpeg integration.

Run the isolated regression checks:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_review_regressions.py tests/test_video_downloader.py tests/test_explicit_filename.py tests/test_truncated_stream.py native_host/tests/test_host.py -q
cd flutter_ui
flutter analyze --no-pub
flutter test --no-pub
```

Several older `*_test.py` files are standalone smoke scripts with real downloads or fixed ports. Browser end-to-end tests need a separately configured browser and native-host installation. They are not covered by the isolated command above. macOS, Linux, and Android release packaging is not currently supported.

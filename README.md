# Download manager

An IDM-style download manager: multi-connection resumable HTTP
downloads, magnet/torrent support, a Windows desktop app, and a Chrome
extension that captures downloads and magnet links from the browser.

## Layout

```
core/               engine: DownloadManager, HTTP + torrent backends (see core/ for its own README notes)
windows_app/         Kivy desktop app shell + local IPC server
browser_extension/   Chrome extension (Manifest V3): capture + interception
native_host/         bridges the extension to the running desktop app
android_app/          Kivy mobile app shell + Android intent-filter capture (see its own README -- libtorrent-on-Android is an open problem)
tests/                core engine integration tests
example_cli.py         terminal demo of the core engine alone
```

## How the pieces connect

```
Chrome extension (background.js)
    -- chrome.runtime.sendNativeMessage -->
native_host/host.py (spawned per-message by Chrome)
    -- HTTP POST /add, localhost only, token-authed -->
windows_app IPC server (runs inside the desktop app process)
    -- in-process call -->
core.DownloadManager
```

The extension never talks to the desktop app directly -- it can't;
browser extensions can't open arbitrary local sockets. Native
messaging is Chrome's sanctioned way to reach a local process, and
`host.py` is deliberately as thin as possible: read one message,
forward it over plain HTTP, relay the response, exit.

## Setup

```
pip install -r requirements.txt
```

### 1. Desktop app

```
python windows_app/main.py
```

Downloads land in `~/.download_manager/downloads`. First run creates
`~/.download_manager/ipc_token.txt` -- the native host needs this file
to exist (i.e. the app needs to have run at least once) before it can
authenticate to the IPC server.

### 2. Browser extension

In Chrome: `chrome://extensions` -> enable Developer mode -> "Load
unpacked" -> select `browser_extension/`. Note the extension ID Chrome
assigns it.

### 3. Native messaging host

```
cd native_host
python register_native_host.py --extension-id <the ID from step 2>
```

On Windows this writes `run_host.bat` + `native_host_manifest.json`
next to `host.py` and registers the manifest under
`HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts` so
Chrome can find it. (On Mac/Linux, the registry step is skipped --
copy the generated manifest into Chrome's `NativeMessagingHosts`
directory for your platform instead; see Chrome's native messaging
docs for the exact path per OS.)

Reload the extension after registering so it picks up the native host.

## What's tested and how

Every piece here was actually exercised, not just written:

- **Core engine**: real multi-connection HTTP download verified
  byte-for-byte (sha256) against a reference download; pause/resume
  verified deterministically against a local throttled server,
  including simulating an app restart mid-download; torrent engine
  verified against real libtorrent sessions and magnet parsing;
  manager's concurrency queueing verified with a real two-task queue.
- **Desktop app**: rendered and screenshotted under Xvfb, with a task
  injected through the real IPC server (simulating the native host)
  and a real segmented HTTP download running in the same UI tick.
- **Browser extension**: loaded in real Chromium via Playwright.
  Confirmed the content script actually prevents magnet-link
  navigation and forwards it, confirmed the background service worker
  correctly calls the native messaging API, and confirmed the full
  chain end-to-end -- real click, real content script, real service
  worker, real OS-level native-messaging-host discovery, real
  `host.py` subprocess, real HTTP round trip to a real IPC server,
  landing as a real task in a real `DownloadManager`. The popup's
  connection status was verified to flip from "not reachable" to
  "Connected" once the host was actually registered.

- **Android app**: same UI/core-reuse pattern as the desktop app,
  tested headlessly under Xvfb with a desktop stub standing in for the
  real Android intent APIs (which can't run outside a device). All
  three ways a download enters the queue -- cold-start intent, a
  live intent while the app's already open, and manual add -- verified
  producing a real task and a real UI row. This testing caught a real
  bug that also affects the Windows app: a malformed magnet link (bad
  info-hash) crashed the whole process instead of failing just that
  one task; now fixed in `core/torrent_engine.py`.

What's *not* covered by these tests, because it's inherently
OS/browser-installation-specific and can't be reproduced in a sandbox:
the Windows registry registration step itself (code is written
carefully but untested on real Windows), real BitTorrent peer
traffic (sandboxed networking here only permits a fixed set of
outbound domains, not arbitrary peer IPs), and everything Android-specific
that requires a real device/emulator (the buildozer build itself, the
pyjnius intent calls, and whether the manifest's intent filters actually
get Android to route magnet taps here -- see `android_app/README.md`).

### 4. Android app

See `android_app/README.md` -- setup, what's tested, and importantly
the libtorrent-on-Android gap (magnet capture works; actually
downloading a magnet doesn't yet, since there's no prebuilt libtorrent
for Android).

## Known gaps (next milestones)

- **libtorrent on Android** -- the single biggest open item. See
  `android_app/README.md` for the options being weighed.
- **System tray icon** for the Windows app (minimize-to-tray,
  IDM-style) -- straightforward addition via `pystray`, not yet built.
- **Global bandwidth throttling** across all active downloads.
- **Torrent resume-data persistence** across app restarts (libtorrent
  supports saving `.fastresume` data; only in-session pause/resume is
  wired up right now).
- The extension's download interception (`chrome.downloads.onCreated`
  + cancel) is implemented but only unit-testable at the message-passing
  level in this sandbox -- worth a manual smoke test with a real file
  download once you're running this in an actual Chrome profile.

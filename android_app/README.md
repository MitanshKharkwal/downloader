# Android app

Same core engine as the Windows app. The only real difference is how
downloads get *in*: there's no browser-extension mechanism on Android
Chrome, so this app instead registers as an OS-level handler for
`magnet:` links and `.torrent` files via an intent filter
(`intent_filters.xml`). Tap either, in any app, and Android routes it
straight here -- no extension, no native messaging host needed.

## Files

```
main.py             Kivy app (touch-sized version of DownloadManagerUI)
intent_bridge.py     pyjnius glue for reading/receiving Android intents,
                      with a desktop stub so this is testable off-device
buildozer.spec        packaging config: permissions, requirements, intent filters
intent_filters.xml     the actual <intent-filter> XML injected into the manifest
tests/                 headless UI test (desktop stub, not a real device)
```

## Building the APK

Requires [buildozer](https://buildozer.readthedocs.io) and the Android
SDK/NDK (buildozer will offer to download these on first build):

```
cd android_app
buildozer android debug
```

This was **not run in this sandbox** -- there's no Android SDK/NDK/emulator
available here, and buildozer's dependencies aren't in this environment's
network allowlist. Every other piece of this app (the UI, the core-engine
reuse, the intent-capture wiring) was tested on a desktop stub, described
below. First real build/install on an actual device or emulator is the
next step, and buildozer errors on a first real build are common enough
(missing SDK components, licenses to accept) that budget some time for it.

## The libtorrent problem (important, unresolved)

**Torrent/magnet downloads do not work on Android yet.** The desktop
apps use `libtorrent`'s Python bindings, which ship prebuilt wheels for
Windows/Mac/Linux -- but there's no prebuilt libtorrent for Android,
and no existing python-for-android recipe to build one. libtorrent is
a large C++ library with a Boost dependency; cross-compiling it for
Android is a real, nontrivial task on its own.

The app **won't crash** if libtorrent is missing -- `core/torrent_engine.py`
detects the failed import and any torrent/magnet add just reports a
clear error on that task instead (this path is tested; see
`core/tests`). But it means magnet capture works (the OS hands the app
the link just fine) while actually downloading it doesn't, yet.

Options, roughly in order of effort:
1. **Write a python-for-android recipe for libtorrent-rasterbar.** The
   real fix, matches the "built-in engine on every platform" goal, but
   is a substantial undertaking (Boost.Build cross-compilation, JNI
   considerations).
2. **Swap in a pure-Python BitTorrent implementation** for the Android
   build specifically (several exist on PyPI) -- less mature/robust
   than libtorrent, but installable via pip/p4a with no native
   compilation.
3. **Delegate**: on Android, when a magnet/.torrent intent comes in,
   offer it to another installed torrent app via
   `Intent.createChooser` instead of handling it internally. Much less
   work, but means Android isn't really running "its own" torrent
   engine -- more of a capture-and-forward.

Worth deciding on this before investing in a real APK build cycle,
since it changes what `requirements` and `android_app/` look like.

## What's tested and how

`tests/test_app_headless.py` runs the real `main.py` under Xvfb
(no Android, no pyjnius) with `intent_bridge` swapped for its desktop
stub, and verifies all three ways a download can enter the queue:

- a simulated cold-start intent (app launched via a tapped magnet link)
- a simulated live intent (app already running, a second link tapped)
- the manual add bar (same as typing a URL by hand)

All three produce a real `DownloadManager` task and a real UI row,
screenshotted for visual confirmation. Along the way this caught a
real bug: a malformed magnet URI (bad info-hash) crashed the whole
app, because `TorrentDownload.start()` didn't catch libtorrent's
parsing exception -- now fixed with a try/except that reports it as a
task error instead. That fix lives in `core/torrent_engine.py` and
applies to the Windows app too, not just Android.

What's **not** and can't be tested here: the actual pyjnius/JNI calls
in `intent_bridge.py` (`mActivity`, `ContentResolver`, etc. only exist
on a running Android process), the buildozer build itself, and the
manifest's intent-filter registration actually working on a real
device. These follow well-documented, standard python-for-android
patterns, but "standard pattern" isn't the same as "verified" --
budget for a round of on-device debugging.

## Known gaps beyond libtorrent

- **Storage permission handling** is minimal -- uses the app-private
  external files directory, which needs no runtime permission on
  modern Android, but means downloads aren't visible in the device's
  general Downloads folder / other apps' file pickers. Worth revisiting
  with `MediaStore` / `ACTION_CREATE_DOCUMENT` if that matters to you.
- **No foreground service**: a long download will likely be paused/killed
  by Android's battery optimization once the app is backgrounded or the
  screen locks. The `FOREGROUND_SERVICE` permission is declared in
  `buildozer.spec` for this reason, but the service itself isn't built.
- **No background/notification UI** -- you have to have the app open to
  see progress; there's no persistent download notification yet.

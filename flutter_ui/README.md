# flutter_ui

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Desktop interface

The Flutter desktop app uses a compact library layout with subtle glass surfaces.
Choose System, Light, or Dark in the sidebar; the preference is saved locally.
Use Ctrl+N to add a download. Search and category/status filters can be combined.

- New download accepts HTTP links, magnets and local torrent files. Advanced options include a destination, JSON request headers and mirror URLs.
- Video / audio supports best video, smallest video and audio-only, with a title lookup.
- Each row supports pause/resume/retry, details, priority, download-first, cancellation and removal. Deleting files requires confirmation.
- Torrent details show peers/seeds and file selection when metadata is available. Resume and refresh details if metadata has not arrived.
- The queue menu provides pause/resume all, clear finished, JSON import/export and service shutdown. Exports exclude private request headers.
- Settings cover destination/category folders, concurrency, bandwidth, schedules, metered connections, archive extraction and startup.

Run `start.bat` from the repository root to start the backend and desktop app. If an older download service is still using port 47821, finish its active downloads and close it before launching this version. The app also warns when it connects to an older service. Glass is rendered inside the Flutter window; it does not blur other applications behind the window.

Frontend verification: `cd flutter_ui` then `flutter analyze --no-pub` and `flutter test --no-pub`.
Set `CAPTURE_UI=1` when running `test/library_test.dart` to save light/dark fixture previews under `flutter_ui/build/previews`.

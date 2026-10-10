import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_ui/models/download_task.dart';
import 'package:flutter_ui/services/ipc_client.dart';
import 'package:flutter_ui/screens/library_screen.dart';
import 'package:flutter_ui/widgets/library_dialogs.dart';
import 'package:flutter_ui/theme/library_theme.dart';

class FakeClient extends IpcClient {
  @override
  Future<Map<String, dynamic>> getConfig() async => {
    'download_dir': 'C:/Downloads',
    'max_concurrent_downloads': 3,
    'global_bandwidth_limit': 0,
    'defender_scan_enabled': false,
    'category_dirs': <String, String>{},
  };
  @override
  Future<Map<String, dynamic>> getSettings() async => {'run_on_startup': false};
  @override
  Future<void> updateSettings(Map<String, dynamic> settings) async {
    await rpc('update_settings', settings);
  }

  final calls = <String>[];
  Map<String, dynamic>? lastArgs;
  bool fail = false;
  @override
  Future<List<DownloadTask>> listTasks() async => [
    DownloadTask(
      id: '1',
      title: 'The creative process.mp4',
      category: TaskCategory.video,
      sizeBytes: 980000000,
      progress: .62,
      speedBytesPerSec: 4200000,
      status: TaskStatus.downloading,
    ),
    DownloadTask(
      id: '2',
      title: 'Collected works.zip',
      category: TaskCategory.compressed,
      sizeBytes: 240000000,
      progress: .3,
      speedBytesPerSec: 0,
      status: TaskStatus.paused,
    ),
    DownloadTask(
      id: '3',
      title: 'Design notes.pdf',
      category: TaskCategory.documents,
      sizeBytes: 12000000,
      progress: 1,
      speedBytesPerSec: 0,
      status: TaskStatus.completed,
    ),
  ];
  @override
  Future<dynamic> rpc(String method, [Map<String, dynamic>? args]) async {
    calls.add(method);
    lastArgs = args;
    if (fail) throw Exception('Service unavailable');
    if (method == 'get_capabilities') return {'ok': true, 'protocol': 2};
    return {'ok': true};
  }
}

class OldServiceClient extends FakeClient {
  @override
  Future<dynamic> rpc(String method, [Map<String, dynamic>? args]) async {
    if (method == 'get_capabilities') throw Exception('Unknown RPC method');
    return super.rpc(method, args);
  }
}

class TorrentDetailClient extends FakeClient {
  @override
  Future<dynamic> rpc(String method, [Map<String, dynamic>? args]) async {
    if (method == 'task_details') {
      return {
        'task': {
          'type': 'torrent',
          'source': 'fixture.torrent',
          'created_at': 0,
          'num_peers': 0,
          'num_seeds': 0,
          'mirrors': [],
          'description': '',
          'files': [
            {
              'name': 'collection/one.txt',
              'size': 3,
              'priority': 4,
              'pad': false,
            },
            {
              'name': 'collection/.pad/123',
              'size': 123,
              'priority': 4,
              'pad': true,
            },
            {
              'name': 'collection/two.txt',
              'size': 3,
              'priority': 4,
              'pad': false,
            },
          ],
        },
      };
    }
    return super.rpc(method, args);
  }
}

class SafetyDetailClient extends FakeClient {
  @override
  Future<dynamic> rpc(String method, [Map<String, dynamic>? args]) async {
    if (method == 'task_details') {
      return {
        'task': {
          'type': 'http',
          'source': 'https://example.invalid/archive.zip',
          'created_at': 0,
          'num_connections': 4,
          'supports_ranges': true,
          'mirrors': [],
          'description': '',
          'health': {
            'state': 'ready',
            'acceleration': '4 connections',
            'supports_ranges': true,
            'effective_connections': 4,
            'cookies_forwarded': true,
          },
          'safety': {
            'status': 'safe',
            'defender': 'clear',
            'sha256': 'abc123',
            'warnings': [],
          },
        },
      };
    }
    return super.rpc(method, args);
  }
}

void main() {
  test('server-denied download has an actionable error', () {
    final task = DownloadTask(
      id: 'denied',
      title: '500MB',
      category: TaskCategory.other,
      sizeBytes: 0,
      progress: 0,
      speedBytesPerSec: 0,
      status: TaskStatus.error,
      errorMessage:
          '403 Client Error: Forbidden for url: https://link.testfile.org/500MB',
    );
    expect(task.errorLabel, contains('Server denied access (HTTP 403)'));
    expect(task.errorLabel, contains('another source'));
  });

  testWidgets('torrent details hide internal padding files', (tester) async {
    final task = DownloadTask(
      id: 'torrent',
      title: 'collection',
      category: TaskCategory.torrents,
      sizeBytes: 6,
      progress: 0,
      speedBytesPerSec: 0,
      status: TaskStatus.paused,
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: Scaffold(
          body: DownloadDetails(client: TorrentDetailClient(), task: task),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('collection/one.txt'), findsOneWidget);
    expect(find.text('collection/two.txt'), findsOneWidget);
    expect(find.textContaining('.pad'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets('old service warns and blocks new download actions', (
    tester,
  ) async {
    final client = OldServiceClient();
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: LibraryScreen(
          client: client,
          mode: ThemeMode.light,
          onModeChanged: (_) {},
        ),
      ),
    );
    await tester.pump();
    expect(find.textContaining('older than this app'), findsOneWidget);
    await tester.tap(find.text('New download').first);
    await tester.pump();
    expect(find.text('File / torrent'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('settings load and save canonical backend options', (
    tester,
  ) async {
    final client = FakeClient();
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: Scaffold(body: PreferencesDialog(client: client)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('C:/Downloads'), findsOneWidget);
    await tester.tap(find.text('Save changes'));
    await tester.pumpAndSettle();
    expect(client.calls, contains('update_settings'));
    expect(client.lastArgs!['max_concurrent_downloads'], 3);
    expect(client.lastArgs!['global_bandwidth_limit'], 0);
    expect(client.lastArgs!['defender_scan_enabled'], false);
    expect(tester.takeException(), isNull);
  });
  testWidgets('download details show health and safety evidence', (
    tester,
  ) async {
    final task = DownloadTask(
      id: 'safe',
      title: 'archive.zip',
      category: TaskCategory.compressed,
      sizeBytes: 10,
      progress: 1,
      speedBytesPerSec: 0,
      status: TaskStatus.completed,
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: Scaffold(
          body: DownloadDetails(client: SafetyDetailClient(), task: task),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Download health'), findsOneWidget);
    expect(find.text('Safety'), findsOneWidget);
    expect(find.text('abc123'), findsOneWidget);
    expect(find.text('4 connections'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('video audio-only selection sends its format to the backend', (
    tester,
  ) async {
    final client = FakeClient()..fail = true;
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.dark),
        home: Scaffold(body: NewDownloadDialog(client: client)),
      ),
    );
    await tester.tap(find.text('Video / audio'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField).first,
      'https://example.com/watch',
    );
    await tester.tap(find.text('Best available video'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Audio only').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Download'));
    await tester.pumpAndSettle();
    expect(client.lastArgs!['format_id'], 'bestaudio');
    expect(client.calls, contains('add_video_task'));
    expect(tester.takeException(), isNull);
  });
  setUpAll(() async {
    final loader = FontLoader('General Sans');
    loader.addFont(rootBundle.load('assets/fonts/GeneralSans-Regular.ttf'));
    await loader.load();
    for (final entry in {
      'MaterialIcons': 'fonts/MaterialIcons-Regular.otf',
      'packages/phosphor_icons/PhosphorLight':
          'packages/phosphor_icons/lib/fonts/Phosphor-Light.ttf',
    }.entries) {
      await (FontLoader(
        entry.key,
      )..addFont(rootBundle.load(entry.value))).load();
    }
  });
  test(
    'unknown-length downloads retain received bytes without inventing ETA',
    () {
      final t = DownloadTask.fromJson({
        'downloaded_bytes': 9000,
        'total_bytes': 0,
        'status': 'DOWNLOADING',
        'speed_bps': 400,
      });
      expect(t.downloadedBytes, 9000);
      expect(t.etaSeconds, isNull);
    },
  );
  for (final brightness in Brightness.values) {
    testWidgets('library ${brightness.name} layout, filters and actions', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final client = FakeClient();
      final key = GlobalKey();
      ThemeMode? selected;
      await tester.pumpWidget(
        MaterialApp(
          theme: libraryTheme(brightness),
          home: RepaintBoundary(
            key: key,
            child: LibraryScreen(
              client: client,
              mode: ThemeMode.system,
              onModeChanged: (v) => selected = v,
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('The creative process.mp4'), findsOneWidget);
      expect(tester.takeException(), isNull);
      if (Platform.environment['CAPTURE_UI'] == '1') {
        final boundary =
            key.currentContext!.findRenderObject() as RenderRepaintBoundary;
        await tester.runAsync(() async {
          final image = await boundary.toImage();
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory('build/previews').create(recursive: true);
          await File(
            'build/previews/${brightness.name}.png',
          ).writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      await tester.tap(find.byTooltip('Light theme'));
      expect(selected, ThemeMode.light);
      await tester.tap(find.byTooltip('Pause'));
      await tester.pump();
      expect(client.calls, contains('pause'));
      await tester.tap(find.text('Paused'));
      await tester.pump();
      expect(find.text('Collected works.zip'), findsOneWidget);
      expect(find.text('The creative process.mp4'), findsNothing);
      await tester.tap(find.text('All').first);
      await tester.pump();
      await tester.enterText(find.byType(TextField), 'notes');
      await tester.pump();
      expect(find.text('Design notes.pdf'), findsOneWidget);
      expect(find.text('Collected works.zip'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('compact library has no overflow', (tester) async {
    tester.view.physicalSize = const Size(640, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: LibraryScreen(
          client: FakeClient(),
          mode: ThemeMode.light,
          onModeChanged: (_) {},
        ),
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  for (final width in [480.0, 320.0]) {
    testWidgets('library fits ${width.toInt()}px width', (tester) async {
      tester.view.physicalSize = Size(width, 560);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          theme: libraryTheme(Brightness.light),
          home: LibraryScreen(
            client: FakeClient(),
            mode: ThemeMode.light,
            onModeChanged: (_) {},
          ),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('add download submits and displays backend errors', (
    tester,
  ) async {
    final client = FakeClient()..fail = true;
    await tester.pumpWidget(
      MaterialApp(
        theme: libraryTheme(Brightness.light),
        home: Scaffold(body: NewDownloadDialog(client: client)),
      ),
    );
    await tester.enterText(
      find.byType(TextField).first,
      'https://example.com/file.zip',
    );
    await tester.tap(find.text('Download'));
    await tester.pumpAndSettle();
    expect(client.calls, ['add_download']);
    expect(client.lastArgs!['source'], 'https://example.com/file.zip');
    expect(find.textContaining('Service unavailable'), findsOneWidget);
    expect(find.text('Download'), findsOneWidget);
  });
}

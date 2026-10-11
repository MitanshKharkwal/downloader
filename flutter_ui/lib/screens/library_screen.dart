import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_selector/file_selector.dart';
import '../models/download_task.dart';
import '../services/ipc_client.dart';
import '../theme/library_theme.dart';
import '../widgets/library_dialogs.dart';

class LibraryScreen extends StatefulWidget {
  const LibraryScreen({
    super.key,
    required this.mode,
    required this.onModeChanged,
    this.client,
    this.compactRows = false,
    this.reduceMotion = false,
    this.onCompactRowsChanged,
    this.onReduceMotionChanged,
  });
  final ThemeMode mode;
  final ValueChanged<ThemeMode> onModeChanged;
  final IpcClient? client;
  final bool compactRows;
  final bool reduceMotion;
  final ValueChanged<bool>? onCompactRowsChanged;
  final ValueChanged<bool>? onReduceMotionChanged;
  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  late final IpcClient client = widget.client ?? IpcClient();
  final search = TextEditingController();
  List<DownloadTask> tasks = [];
  String section = 'All downloads';
  String filter = 'All';
  bool connected = true, loading = true, fetching = false;
  bool? serviceCompatible;
  final Set<String> pending = {};
  final Set<String> selected = {};
  bool selecting = false;
  Timer? timer;
  Timer? updateTimer;
  String? availableUpdate;
  int failures = 0;
  DateTime retryAt = DateTime(2000);

  @override
  void initState() {
    super.initState();
    refresh();
    timer = Timer.periodic(const Duration(seconds: 1), (_) => refresh());
    updateTimer = Timer(const Duration(seconds: 5), checkUpdates);
  }

  @override
  void dispose() {
    timer?.cancel();
    updateTimer?.cancel();
    search.dispose();
    super.dispose();
  }

  Future<void> checkUpdates() async {
    if (serviceCompatible == false) return;
    try {
      final response = await client.rpc('check_for_updates');
      final update = Map<String, dynamic>.from(response['update'] ?? {});
      if (mounted) {
        setState(() {
          availableUpdate = update['available'] == true
              ? update['version']?.toString()
              : null;
        });
      }
    } catch (_) {
      // Update checks are silent; the Updates dialog shows actionable errors.
    }
  }

  Future<void> refresh({bool force = false}) async {
    if (fetching || (!force && DateTime.now().isBefore(retryAt))) return;
    fetching = true;
    try {
      final result = await client.listTasks();
      var compatible = serviceCompatible;
      if (compatible != true) {
        try {
          final response = await client.rpc('get_capabilities');
          compatible = response['protocol'] == 2;
        } catch (_) {
          compatible = false;
        }
      }
      failures = 0;
      if (mounted) {
        setState(() {
          tasks = result;
          selected.removeWhere((id) => !result.any((task) => task.id == id));
          connected = true;
          serviceCompatible = compatible;
          loading = false;
        });
      }
    } catch (_) {
      failures = (failures + 1).clamp(1, 5);
      retryAt = DateTime.now().add(Duration(seconds: 1 << failures));
      if (mounted) {
        setState(() {
          connected = false;
          serviceCompatible = null;
          loading = false;
        });
      }
    } finally {
      fetching = false;
    }
  }

  Future<void> action(String key, Future<void> Function() fn) async {
    if (serviceCompatible == false) return;
    if (pending.contains(key)) return;
    setState(() => pending.add(key));
    try {
      await fn();
      await refresh(force: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => pending.remove(key));
    }
  }

  Future<void> add() async {
    if (serviceCompatible == false) return;
    await showDialog<void>(
      context: context,
      builder: (_) => NewDownloadDialog(client: client),
    );
    await refresh(force: true);
  }

  Future<bool> confirm(
    String title,
    String text, {
    String actionLabel = 'Continue',
  }) async =>
      await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(text),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Keep'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(actionLabel),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> taskAction(DownloadTask task, String method) async {
    if (serviceCompatible == false) return;
    if (method == 'details') {
      await showDialog<void>(
        context: context,
        builder: (_) => DownloadDetails(client: client, task: task),
      );
      return;
    }
    if (method == 'reveal') {
      await action(task.id, () async {
        final result = await Process.run('explorer.exe', [
          '/select,',
          task.filePath!,
        ]);
        if (result.exitCode != 0 && result.exitCode != 1) {
          throw Exception('Could not open the download folder.');
        }
      });
      return;
    }
    if (method == 'open' || method == 'open_with') {
      await action(task.id, () async {
        final path = task.filePath;
        if (path == null ||
            path.isEmpty ||
            await FileSystemEntity.type(path) ==
                FileSystemEntityType.notFound) {
          throw Exception('The downloaded file is no longer available.');
        }
        if (method == 'open_with' && FileSystemEntity.isFileSync(path)) {
          await Process.start('rundll32.exe', [
            'shell32.dll,OpenAs_RunDLL',
            path,
          ], mode: ProcessStartMode.detached);
        } else {
          await Process.start('explorer.exe', [
            path,
          ], mode: ProcessStartMode.detached);
        }
      });
      return;
    }
    if (method == 'cancel' || method == 'delete') {
      if (!await confirm(
        method == 'delete'
            ? 'Delete downloaded files?'
            : 'Cancel this download?',
        method == 'delete'
            ? 'This removes the download and its files from your computer.'
            : 'Partial files will be kept. You can retry later.',
      )) {
        return;
      }
    }
    await action(task.id, () async {
      await client.rpc(method == 'delete' ? 'remove_task' : method, {
        'task_id': task.id,
        if (method == 'delete') 'delete_files': true,
      });
    });
  }

  void toggleSelection(DownloadTask task) {
    setState(() {
      selecting = true;
      if (!selected.add(task.id)) selected.remove(task.id);
    });
  }

  void leaveSelection() => setState(() {
    selecting = false;
    selected.clear();
  });

  Future<void> removeSelected({required bool deleteFiles}) async {
    if (selected.isEmpty) return;
    final count = selected.length;
    final approved = await confirm(
      deleteFiles
          ? 'Delete $count selected downloads?'
          : 'Remove $count selected downloads?',
      deleteFiles
          ? 'The selected entries and their downloaded or partial files will be permanently removed.'
          : 'The selected entries will leave the app. Downloaded files will stay on your computer.',
      actionLabel: deleteFiles ? 'Delete files' : 'Remove',
    );
    if (!approved || !mounted) return;
    final ids = selected.toList(growable: false);
    await action('selection', () async {
      await client.rpc('remove_tasks', {
        'task_ids': ids,
        'delete_files': deleteFiles,
      });
      if (mounted) leaveSelection();
    });
  }

  Future<void> queueAction(String method) async {
    if (serviceCompatible == false) return;
    if (method == 'clear_finished' &&
        !await confirm(
          'Clear finished downloads?',
          'Completed, canceled and failed entries will be removed. Your files stay on disk.',
        )) {
      return;
    }
    if (method == 'shutdown' &&
        !await confirm(
          'Stop the download service?',
          'Downloads will pause. Restart the app launcher to reconnect.',
        )) {
      return;
    }
    await action('queue', () async {
      String? path;
      if (method == 'import_queue') {
        path = (await openFile(
          acceptedTypeGroups: [
            const XTypeGroup(label: 'Download queue', extensions: ['json']),
          ],
        ))?.path;
        if (path == null) return;
      } else if (method == 'export_queue') {
        path = (await getSaveLocation(
          suggestedName: 'downloads.json',
          acceptedTypeGroups: [
            const XTypeGroup(label: 'Download queue', extensions: ['json']),
          ],
        ))?.path;
        if (path == null) return;
      }
      final result = await client.rpc(method, {'file_path': ?path});
      if (mounted && (method == 'import_queue' || method == 'export_queue')) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              method == 'import_queue'
                  ? '${result['imported']} downloads imported. ${result['failed']} skipped.'
                  : 'Queue exported. Private headers are excluded.',
            ),
          ),
        );
      }
    });
  }

  List<DownloadTask> get visible => tasks.where((t) {
    final category = section == 'All downloads' || t.category.label == section;
    final status = switch (filter) {
      'Active' =>
        t.status == TaskStatus.downloading ||
            t.status == TaskStatus.connecting ||
            t.status == TaskStatus.queued,
      'Paused' => t.status == TaskStatus.paused,
      'Finished' => t.status == TaskStatus.completed,
      'Failed' =>
        t.status == TaskStatus.error || t.status == TaskStatus.canceled,
      _ => true,
    };
    return category &&
        status &&
        t.title.toLowerCase().contains(search.text.toLowerCase());
  }).toList();

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyN, control: true): add,
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          body: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color.alphaBlend(
                    c.primary.withValues(alpha: .035),
                    c.surface,
                  ),
                  c.surface,
                  c.surface,
                ],
                stops: const [0, .38, 1],
              ),
            ),
            child: LayoutBuilder(
              builder: (context, size) {
                final narrow = size.maxWidth < 850;
                return Row(
                  children: [
                    SizedBox(width: narrow ? 76 : 224, child: sidebar(narrow)),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Glass(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 24,
                                vertical: 16,
                              ),
                              child: selecting
                                  ? Row(
                                      children: [
                                        IconButton(
                                          tooltip: 'Exit selection',
                                          onPressed: leaveSelection,
                                          icon: const Icon(Icons.close_rounded),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Text(
                                            '${selected.length} selected',
                                            style: const TextStyle(
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                        if (size.maxWidth < 600)
                                          PopupMenuButton<String>(
                                            tooltip: 'Selection actions',
                                            onSelected: (action) {
                                              switch (action) {
                                                case 'all':
                                                  setState(() {
                                                    selected.addAll(
                                                      visible.map(
                                                        (task) => task.id,
                                                      ),
                                                    );
                                                  });
                                                  return;
                                                case 'remove':
                                                  removeSelected(
                                                    deleteFiles: false,
                                                  );
                                                  return;
                                                case 'delete':
                                                  removeSelected(
                                                    deleteFiles: true,
                                                  );
                                                  return;
                                              }
                                            },
                                            itemBuilder: (_) => [
                                              const PopupMenuItem(
                                                value: 'all',
                                                child: Text('Select all visible'),
                                              ),
                                              PopupMenuItem(
                                                value: 'remove',
                                                enabled: selected.isNotEmpty,
                                                child: const Text(
                                                  'Remove from app',
                                                ),
                                              ),
                                              PopupMenuItem(
                                                value: 'delete',
                                                enabled: selected.isNotEmpty,
                                                child: const Text(
                                                  'Delete files and entries',
                                                ),
                                              ),
                                            ],
                                          )
                                        else ...[
                                          IconButton(
                                            tooltip: 'Select all visible',
                                            onPressed: () => setState(() {
                                              selected.addAll(
                                                visible.map((task) => task.id),
                                              );
                                            }),
                                            icon: const Icon(
                                              Icons.select_all_rounded,
                                            ),
                                          ),
                                          IconButton(
                                            tooltip: 'Remove from app',
                                            onPressed: selected.isEmpty
                                                ? null
                                                : () => removeSelected(
                                                    deleteFiles: false,
                                                  ),
                                            icon: const Icon(
                                              Icons.remove_circle_outline_rounded,
                                            ),
                                          ),
                                          IconButton(
                                            tooltip: 'Delete files and entries',
                                            onPressed: selected.isEmpty
                                                ? null
                                                : () => removeSelected(
                                                    deleteFiles: true,
                                                  ),
                                            icon: const Icon(
                                              Icons.delete_outline_rounded,
                                            ),
                                          ),
                                        ],
                                      ],
                                    )
                                  : Row(
                                      children: [
                                        Expanded(
                                          child: TextField(
                                            controller: search,
                                            onChanged: (_) => setState(() {}),
                                            decoration: const InputDecoration(
                                              hintText: 'Search downloads',
                                              prefixIcon: Icon(
                                                Icons.search_rounded,
                                                size: 21,
                                              ),
                                              border: OutlineInputBorder(
                                                borderRadius: BorderRadius.all(
                                                  Radius.circular(12),
                                                ),
                                                borderSide: BorderSide.none,
                                              ),
                                              enabledBorder: OutlineInputBorder(
                                                borderRadius: BorderRadius.all(
                                                  Radius.circular(12),
                                                ),
                                                borderSide: BorderSide.none,
                                              ),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        IconButton(
                                          tooltip: 'Select downloads',
                                          onPressed: serviceCompatible == false
                                              ? null
                                              : () => setState(
                                                  () => selecting = true,
                                                ),
                                          icon: const Icon(
                                            Icons.checklist_rounded,
                                          ),
                                        ),
                                        PopupMenuButton<String>(
                                          tooltip: 'Queue actions',
                                          enabled:
                                              serviceCompatible != false &&
                                              !pending.contains('queue'),
                                          onSelected: queueAction,
                                          itemBuilder: (_) => [
                                            for (final entry in {
                                              'pause_all': 'Pause all',
                                              'resume_all': 'Resume all',
                                              'clear_finished':
                                                  'Clear finished',
                                              'import_queue': 'Import queue…',
                                              'export_queue': 'Export queue…',
                                              'shutdown': 'Stop service…',
                                            }.entries)
                                              PopupMenuItem(
                                                value: entry.key,
                                                child: Text(entry.value),
                                              ),
                                          ],
                                          icon: const Icon(
                                            Icons.more_horiz_rounded,
                                          ),
                                        ),
                                      ],
                                    ),
                            ),
                          ),
                          if (!connected)
                            MaterialBanner(
                              content: const Text(
                                'Download service unavailable. Reconnecting…',
                              ),
                              actions: [
                                TextButton(
                                  onPressed: () => refresh(force: true),
                                  child: const Text('Retry'),
                                ),
                              ],
                            ),
                          if (connected && serviceCompatible == false)
                            MaterialBanner(
                              content: const Text(
                                'The running download service is older than this app. Finish active downloads, close the old service, then launch the updated app with start.bat.',
                              ),
                              actions: [
                                TextButton(
                                  onPressed: () {
                                    setState(() => serviceCompatible = null);
                                    refresh(force: true);
                                  },
                                  child: const Text('Recheck'),
                                ),
                              ],
                            ),
                          Padding(
                            padding: const EdgeInsets.fromLTRB(30, 30, 30, 22),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        section,
                                        style: const TextStyle(
                                          fontSize: 30,
                                          fontWeight: FontWeight.w700,
                                          letterSpacing: -1,
                                        ),
                                      ),
                                      const SizedBox(height: 6),
                                      Text(
                                        '${visible.length} items · ${tasks.where((t) => t.status.isActive).length} downloading',
                                        style: TextStyle(
                                          color: c.onSurfaceVariant,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                if (size.maxWidth > 600)
                                  FilledButton.icon(
                                    onPressed: serviceCompatible == false
                                        ? null
                                        : add,
                                    icon: const Icon(
                                      Icons.add_rounded,
                                      size: 19,
                                    ),
                                    label: const Text('New download'),
                                  ),
                              ],
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 30),
                            child: SingleChildScrollView(
                              scrollDirection: Axis.horizontal,
                              child: Row(
                                children: [
                                  for (final name in [
                                    'All',
                                    'Active',
                                    'Paused',
                                    'Finished',
                                    'Failed',
                                  ])
                                    Padding(
                                      padding: const EdgeInsets.only(right: 8),
                                      child: ChoiceChip(
                                        label: Text(name),
                                        selected: filter == name,
                                        showCheckmark: false,
                                        onSelected: (_) =>
                                            setState(() => filter = name),
                                        side: BorderSide.none,
                                        selectedColor: c.onSurface.withValues(
                                          alpha: .09,
                                        ),
                                        backgroundColor: Colors.transparent,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          Expanded(
                            child: loading
                                ? const Center(
                                    child: CircularProgressIndicator(),
                                  )
                                : visible.isEmpty
                                ? empty()
                                : ListView.separated(
                                    padding: const EdgeInsets.fromLTRB(
                                      22,
                                      0,
                                      22,
                                      24,
                                    ),
                                    itemCount: visible.length,
                                    separatorBuilder: (_, _) => Divider(
                                      height: 1,
                                      indent: 68,
                                      color: c.outlineVariant.withValues(
                                        alpha: .45,
                                      ),
                                    ),
                                    itemBuilder: (_, i) => downloadRow(
                                      visible[i],
                                      size.maxWidth < 1000,
                                    ),
                                  ),
                          ),
                          Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 30,
                              vertical: 14,
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  Icons.circle,
                                  size: 7,
                                  color: connected ? c.primary : c.error,
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  !connected
                                      ? 'Offline'
                                      : serviceCompatible == false
                                      ? 'Service update needed'
                                      : 'Service connected',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: c.onSurfaceVariant,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  '${DownloadTask.formatBytes(tasks.fold<double>(0, (s, t) => s + t.speedBytesPerSec).round())}/s',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: c.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget sidebar(bool narrow) {
    final c = Theme.of(context).colorScheme;
    Widget nav(String title, IconData icon, {int? count}) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
      child: Tooltip(
        message: narrow ? title : '',
        child: Material(
          color: section == title
              ? c.onSurface.withValues(alpha: .075)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => setState(() => section = title),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              child: Row(
                children: [
                  Icon(
                    icon,
                    size: 21,
                    color: section == title ? c.primary : c.onSurfaceVariant,
                  ),
                  if (!narrow) ...[
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        title,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: section == title
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                    ),
                    if (count != null && count > 0)
                      Text(
                        '$count',
                        style: TextStyle(
                          fontSize: 11,
                          color: c.onSurfaceVariant,
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
    return Glass(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(narrow ? 24 : 26, 30, 16, 30),
            child: Row(
              children: [
                Icon(Icons.downloading_rounded, color: c.primary, size: 28),
                if (!narrow) ...[
                  const SizedBox(width: 10),
                  const Text(
                    'Fetchly',
                    style: TextStyle(
                      fontSize: 23,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -.8,
                    ),
                  ),
                ],
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14),
            child: narrow
                ? IconButton.filled(
                    onPressed: serviceCompatible == false ? null : add,
                    tooltip: 'New download',
                    icon: const Icon(Icons.add_rounded),
                  )
                : OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 14,
                      ),
                    ),
                    onPressed: serviceCompatible == false ? null : add,
                    icon: const Icon(Icons.add_rounded, size: 18),
                    label: const Text('New download'),
                  ),
          ),
          const SizedBox(height: 28),
          if (!narrow)
            Padding(
              padding: const EdgeInsets.fromLTRB(26, 0, 0, 10),
              child: Text(
                'LIBRARY',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.4,
                  fontWeight: FontWeight.w600,
                  color: c.onSurfaceVariant,
                ),
              ),
            ),
          Expanded(
            child: ListView(
              children: [
                nav(
                  'All downloads',
                  Icons.layers_outlined,
                  count: tasks.length,
                ),
                const SizedBox(height: 14),
                for (final category in TaskCategory.values)
                  nav(
                    category.label,
                    category.icon,
                    count: tasks.where((t) => t.category == category).length,
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                if (!narrow)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Padding(
                      padding: const EdgeInsets.only(left: 12, bottom: 8),
                      child: Text(
                        'Appearance',
                        style: TextStyle(
                          fontSize: 11,
                          color: c.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    if (narrow)
                      PopupMenuButton<ThemeMode>(
                        tooltip: 'Appearance',
                        onSelected: widget.onModeChanged,
                        icon: const Icon(Icons.contrast_rounded),
                        itemBuilder: (_) => [
                          for (final m in ThemeMode.values)
                            PopupMenuItem(value: m, child: Text(m.name)),
                        ],
                      )
                    else
                      for (final m in ThemeMode.values)
                        IconButton(
                          tooltip:
                              '${m.name[0].toUpperCase()}${m.name.substring(1)} theme',
                          isSelected: widget.mode == m,
                          style: IconButton.styleFrom(
                            backgroundColor: widget.mode == m
                                ? c.onSurface.withValues(alpha: .08)
                                : Colors.transparent,
                          ),
                          onPressed: () => widget.onModeChanged(m),
                          icon: Icon(switch (m) {
                            ThemeMode.system => Icons.brightness_auto_outlined,
                            ThemeMode.light => Icons.light_mode_outlined,
                            ThemeMode.dark => Icons.dark_mode_outlined,
                          }, size: 19),
                        ),
                  ],
                ),
                TextButton(
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => AppearanceDialog(
                      mode: widget.mode,
                      compactRows: widget.compactRows,
                      reduceMotion: widget.reduceMotion,
                      onModeChanged: widget.onModeChanged,
                      onCompactRowsChanged:
                          widget.onCompactRowsChanged ?? (_) {},
                      onReduceMotionChanged:
                          widget.onReduceMotionChanged ?? (_) {},
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: narrow
                        ? MainAxisAlignment.center
                        : MainAxisAlignment.start,
                    children: [
                      const Icon(Icons.palette_outlined, size: 20),
                      if (!narrow) ...[
                        const SizedBox(width: 12),
                        const Text('Display options'),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: serviceCompatible == false
                      ? null
                      : () => showDialog<void>(
                          context: context,
                          builder: (_) => PreferencesDialog(client: client),
                        ),
                  child: Row(
                    mainAxisAlignment: narrow
                        ? MainAxisAlignment.center
                        : MainAxisAlignment.start,
                    children: [
                      const Icon(Icons.tune_rounded, size: 20),
                      if (!narrow) ...[
                        const SizedBox(width: 12),
                        const Text('Settings'),
                      ],
                    ],
                  ),
                ),
                TextButton(
                  onPressed: serviceCompatible == false
                      ? null
                      : () async {
                          await showDialog<void>(
                            context: context,
                            builder: (_) => UpdateDialog(client: client),
                          );
                          await checkUpdates();
                        },
                  child: Row(
                    mainAxisAlignment: narrow
                        ? MainAxisAlignment.center
                        : MainAxisAlignment.start,
                    children: [
                      Badge(
                        isLabelVisible: availableUpdate != null,
                        child: const Icon(
                          Icons.system_update_alt_rounded,
                          size: 20,
                        ),
                      ),
                      if (!narrow) ...[
                        const SizedBox(width: 12),
                        Text(
                          availableUpdate == null
                              ? 'Updates'
                              : 'Update $availableUpdate',
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget empty() => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.file_download_outlined,
            size: 48,
            color: Theme.of(
              context,
            ).colorScheme.onSurfaceVariant.withValues(alpha: .5),
          ),
          const SizedBox(height: 20),
          Text(
            tasks.isEmpty
                ? 'A place for your downloads'
                : 'No matching downloads',
            style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 10),
          Text(
            tasks.isEmpty
                ? 'Add a link. We’ll take care of the rest.'
                : 'Try another category, filter or search.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          if (tasks.isEmpty)
            FilledButton.icon(
              onPressed: serviceCompatible == false ? null : add,
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add your first download'),
            ),
        ],
      ),
    ),
  );

  Widget downloadRow(DownloadTask t, bool compact) {
    final c = Theme.of(context).colorScheme;
    final busy = pending.contains(t.id);
    final active =
        t.status == TaskStatus.downloading ||
        t.status == TaskStatus.connecting ||
        t.status == TaskStatus.queued;
    final failed =
        t.status == TaskStatus.error || t.status == TaskStatus.canceled;
    final hasFile =
        t.status == TaskStatus.completed &&
        t.filePath != null &&
        t.filePath!.isNotEmpty;
    final primary = active
        ? 'pause'
        : failed
        ? 'retry'
        : 'resume';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => selecting ? toggleSelection(t) : taskAction(t, 'details'),
        onLongPress: () => toggleSelection(t),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: 8,
            vertical: widget.compactRows ? 11 : 20,
          ),
          child: Row(
            children: [
              if (selecting) ...[
                Checkbox(
                  value: selected.contains(t.id),
                  onChanged: (_) => toggleSelection(t),
                ),
                const SizedBox(width: 4),
              ],
              Tooltip(
                message: hasFile
                    ? 'Open ${t.title}'
                    : 'Available when the download finishes',
                child: Material(
                  color: c.primary.withValues(alpha: .07),
                  borderRadius: BorderRadius.circular(12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: hasFile ? () => taskAction(t, 'open') : null,
                    child: SizedBox(
                      width: 46,
                      height: widget.compactRows ? 42 : 50,
                      child: Icon(t.category.icon, color: c.primary, size: 23),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 18),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      t.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 7),
                    Text(
                      t.status == TaskStatus.error
                          ? t.errorLabel
                          : '${t.status.label} · ${DownloadTask.formatBytes(t.downloadedBytes)}${t.sizeBytes > 0 ? ' of ${t.sizeLabel}' : ''}${!compact && active ? ' · ${t.etaLabel} remaining' : ''}',
                      maxLines: t.status == TaskStatus.error ? 2 : 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        color: t.status == TaskStatus.error
                            ? c.error
                            : c.onSurfaceVariant,
                      ),
                    ),
                    if (active || t.status == TaskStatus.paused) ...[
                      const SizedBox(height: 11),
                      SizedBox(
                        width: 380,
                        child: LinearProgressIndicator(
                          value: t.sizeBytes > 0
                              ? t.progress
                              : (active ? null : 0),
                          minHeight: 3,
                          borderRadius: BorderRadius.circular(3),
                          backgroundColor: c.onSurface.withValues(alpha: .07),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              if (!compact)
                SizedBox(
                  width: 110,
                  child: Text(
                    t.speedLabel,
                    textAlign: TextAlign.right,
                    style: TextStyle(fontSize: 12, color: c.onSurfaceVariant),
                  ),
                ),
              const SizedBox(width: 12),
              if (selecting)
                const SizedBox.shrink()
              else if (busy)
                const SizedBox(
                  width: 40,
                  height: 24,
                  child: Center(
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                )
              else if (hasFile)
                IconButton(
                  tooltip: 'Show in folder',
                  onPressed: serviceCompatible == false
                      ? null
                      : () => taskAction(t, 'reveal'),
                  icon: const Icon(Icons.folder_open_rounded, size: 20),
                )
              else
                IconButton(
                  tooltip: active
                      ? 'Pause'
                      : failed
                      ? 'Retry'
                      : 'Resume',
                  onPressed: serviceCompatible == false
                      ? null
                      : () => taskAction(t, primary),
                  icon: Icon(
                    active
                        ? Icons.pause_rounded
                        : failed
                        ? Icons.refresh_rounded
                        : Icons.play_arrow_rounded,
                    size: 22,
                  ),
                ),
              if (!selecting) PopupMenuButton<String>(
                tooltip: 'Download actions',
                enabled: serviceCompatible != false && !busy,
                onSelected: (m) => taskAction(t, m),
                itemBuilder: (_) => [
                  if (hasFile)
                    const PopupMenuItem(
                      value: 'open',
                      child: Text('Open file'),
                    ),
                  if (hasFile)
                    const PopupMenuItem(
                      value: 'open_with',
                      child: Text('Open with…'),
                    ),
                  if (hasFile)
                    const PopupMenuItem(
                      value: 'reveal',
                      child: Text('Show in folder'),
                    ),
                  const PopupMenuItem(
                    value: 'details',
                    child: Text('Details & priority'),
                  ),
                  if (active || t.status == TaskStatus.paused)
                    const PopupMenuItem(
                      value: 'set_urgent',
                      child: Text('Download first'),
                    ),
                  if (active || t.status == TaskStatus.paused)
                    const PopupMenuItem(
                      value: 'cancel',
                      child: Text('Cancel download…'),
                    ),
                  if (!active && t.status != TaskStatus.paused)
                    const PopupMenuItem(
                      value: 'remove_task',
                      child: Text('Remove from list'),
                    ),
                  const PopupMenuItem(
                    value: 'delete',
                    child: Text('Delete files…'),
                  ),
                ],
                icon: const Icon(Icons.more_horiz_rounded, size: 20),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

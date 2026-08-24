import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:phosphor_icons/phosphor_icons.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/ipc_client.dart';
import '../widgets/add_url_dialog.dart';
import '../models/download_task.dart';
import '../theme/app_theme.dart';
import '../widgets/empty_state.dart';
import '../widgets/sidebar.dart';
import '../widgets/task_list.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final IpcClient _ipcClient = IpcClient();
  List<DownloadTask> _all = <DownloadTask>[];
  List<DownloadTask> _visible = <DownloadTask>[];
  bool _isConnected = true;
  
  final TextEditingController _searchController = TextEditingController();

  int _selectedNav = 0;
  String _query = '';
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _fetchTasks();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => _fetchTasks());
    _checkFirstRun();
  }

  Future<void> _checkFirstRun() async {
    final prefs = await SharedPreferences.getInstance();
    final hasRun = prefs.getBool('hasRunBefore') ?? false;
    if (!hasRun) {
      await prefs.setBool('hasRunBefore', true);
      if (mounted) {
        _showNativeHostDialog();
      }
    }
  }

  void _showNativeHostDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppColors.surface,
          title: const Text('Setup Browser Extension', style: TextStyle(color: AppColors.textPrimary)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'To capture downloads directly from Chrome, you need to register the native messaging host. Install the extension in Chrome, copy its ID, and run the following command in your terminal:',
                style: TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppColors.background,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const SelectableText(
                  'cd native_host && .\\register-native-host.exe --extension-id <YOUR_EXTENSION_ID>',
                  style: TextStyle(color: AppColors.textPrimary, fontFamily: 'monospace'),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Clipboard.setData(const ClipboardData(text: 'cd native_host && .\\register-native-host.exe --extension-id '));
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Command copied!')));
              },
              child: const Text('Copy Command', style: TextStyle(color: AppColors.accent)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.accent),
              onPressed: () => Navigator.pop(context),
              child: const Text('Got it', style: TextStyle(color: AppColors.textPrimary)),
            ),
          ],
        );
      },
    );
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _fetchTasks() async {
    try {
      final tasks = await _ipcClient.listTasks();
      if (mounted) {
        setState(() {
          _isConnected = true;
          _all = tasks;
          _visible = _filtered();
        });
      }
    } catch (e) {
      if (mounted && _isConnected) {
        setState(() => _isConnected = false);
      }
    }
  }

  List<DownloadTask> _filtered() {
    final TaskCategory? category = kNavItems[_selectedNav].category;
    final String q = _query.trim().toLowerCase();
    return _all.where((DownloadTask t) {
      final bool matchesCategory = category == null || t.category == category;
      final bool matchesQuery = q.isEmpty || t.title.toLowerCase().contains(q);
      return matchesCategory && matchesQuery;
    }).toList();
  }

  void _resyncList() {
    setState(() {
      _visible = _filtered();
    });
  }

  Map<int, int> _counts() {
    final Map<int, int> counts = <int, int>{0: _all.length};
    for (int i = 1; i < kNavItems.length; i++) {
      final TaskCategory? category = kNavItems[i].category;
      counts[i] = _all.where((DownloadTask t) => t.category == category).length;
    }
    return counts;
  }

  void _addTask() {
    showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Dismiss',
      barrierColor: Colors.black54,
      transitionDuration: const Duration(milliseconds: 180),
      pageBuilder: (BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation) {
        return AddUrlDialog(
          onAdd: (String url) async {
            await _ipcClient.addUrl(url);
            _fetchTasks();
          },
        );
      },
      transitionBuilder: (BuildContext context, Animation<double> animation, Animation<double> secondaryAnimation, Widget child) {
        final double curve = Curves.easeOutCubic.transform(animation.value);
        return Opacity(
          opacity: curve,
          child: Transform.scale(
            scale: 0.95 + (0.05 * curve),
            child: child,
          ),
        );
      },
    );
  }

  void _openSettings() {
    showDialog<void>(
      context: context,
      barrierColor: Colors.black54,
      builder: (BuildContext context) => Dialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.lg,
          side: const BorderSide(color: AppColors.border),
        ),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Settings', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(
                'Download location, bandwidth limits and connection settings would live here.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: AppColors.textMuted, height: 1.5),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final bool collapsed = constraints.maxWidth < 900;
          final bool compact = constraints.maxWidth < 760;

          return Stack(
            children: <Widget>[
              Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Sidebar(
                    selected: _selectedNav,
                    counts: _counts(),
                    collapsed: collapsed,
                    onSelect: (int index) {
                      if (index == _selectedNav) return;
                      _selectedNav = index;
                      _resyncList();
                    },
                    onNewDownload: _addTask,
                    onSettings: _openSettings,
                  ),
                  Expanded(child: _buildMain(compact)),
                ],
              ),
              AnimatedPositioned(
                duration: AppTheme.medium,
                curve: Curves.easeOutCubic,
                top: _isConnected ? -60 : 0,
                left: 0,
                right: 0,
                height: 48,
                child: Container(
                  alignment: Alignment.center,
                  decoration: const BoxDecoration(
                    color: AppColors.danger,
                    boxShadow: <BoxShadow>[
                      BoxShadow(color: Colors.black26, blurRadius: 8, offset: Offset(0, 4)),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Icon(PhosphorIcons.warningCircle(PhosphorIconsStyle.fill), color: Colors.white, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'Daemon disconnected. Retrying connection...',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 13),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildMain(bool compact) {
    final NavItem item = kNavItems[_selectedNav];
    final int activeCount = _visible.where((DownloadTask t) => t.status == TaskStatus.downloading).length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Header(
          title: item.label,
          subtitle: _visible.isEmpty
              ? 'Nothing here yet'
              : '${_visible.length} item${_visible.length == 1 ? '' : 's'} · $activeCount active',
          controller: _searchController,
          onQueryChanged: (String value) {
            _query = value;
            _resyncList();
          },
          compact: compact,
        ),
        if (_visible.isNotEmpty) TaskListHeader(compact: compact),
        Expanded(
          child: _visible.isEmpty
              ? EmptyState(
                  title: _query.trim().isEmpty ? 'No active tasks' : 'No results found',
                  subtitle: _query.trim().isEmpty
                      ? 'Click the button below or press Ctrl+N to add a new download.'
                      : 'Try adjusting your search or filters.',
                  icon: _query.trim().isEmpty
                      ? PhosphorIcons.tray(PhosphorIconsStyle.light)
                      : PhosphorIcons.magnifyingGlassMinus(PhosphorIconsStyle.light),
                  onAction: _query.trim().isEmpty ? _addTask : null,
                  actionLabel: 'New Download',
                )
              : TaskList(
                  tasks: _visible,
                  compact: compact,
                  onPause: (DownloadTask t) async {
                    await _ipcClient.pauseTask(t.id);
                    _fetchTasks();
                  },
                  onResume: (DownloadTask t) async {
                    await _ipcClient.resumeTask(t.id);
                    _fetchTasks();
                  },
                  onRetry: (DownloadTask t) async {
                    await _ipcClient.retryTask(t.id);
                    _fetchTasks();
                  },
                  onCancel: (DownloadTask t) async {
                    await _ipcClient.cancelTask(t.id);
                    _fetchTasks();
                  },
                  onRemove: (DownloadTask t) async {
                    await _ipcClient.removeTask(t.id);
                    _fetchTasks();
                  },
                  onPriority: (DownloadTask t, int p) async {
                    await _ipcClient.setPriority(t.id, p);
                    _fetchTasks();
                  },
                ),
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.title,
    required this.subtitle,
    required this.controller,
    required this.onQueryChanged,
    required this.compact,
  });

  final String title;
  final String subtitle;
  final TextEditingController controller;
  final ValueChanged<String> onQueryChanged;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(28, 26, 28, 20),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: text.headlineMedium?.copyWith(
                    fontSize: compact ? 22 : 26,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  style: text.bodySmall?.copyWith(
                    color: AppColors.textMuted,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          SizedBox(
            width: compact ? 160 : 260,
            child: TextField(
              controller: controller,
              onChanged: onQueryChanged,
              style: text.bodySmall?.copyWith(fontSize: 13),
              decoration: InputDecoration(
                hintText: 'Search downloads…',
                prefixIcon: Icon(
                  PhosphorIcons.magnifyingGlass(PhosphorIconsStyle.light),
                  size: 16,
                  color: AppColors.textMuted,
                ),
                prefixIconConstraints: const BoxConstraints(
                  minWidth: 36,
                  minHeight: 36,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

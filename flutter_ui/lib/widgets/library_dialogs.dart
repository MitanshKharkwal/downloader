import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:file_selector/file_selector.dart';
import '../services/ipc_client.dart';
import '../models/download_task.dart';
import '../theme/library_theme.dart';

class NewDownloadDialog extends StatefulWidget {
  const NewDownloadDialog({super.key, required this.client});
  final IpcClient client;
  @override
  State<NewDownloadDialog> createState() => _NewDownloadDialogState();
}

class _NewDownloadDialogState extends State<NewDownloadDialog> {
  final source = TextEditingController(),
      filename = TextEditingController(),
      destination = TextEditingController(),
      headers = TextEditingController(),
      mirrors = TextEditingController();
  String kind = 'File', quality = 'best';
  String? error, videoTitle;
  String? inspectedTorrent;
  Map<String, dynamic>? torrentInfo;
  List<int> torrentPriorities = [];
  bool busy = false;
  @override
  void dispose() {
    for (final c in [source, filename, destination, headers, mirrors]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> submit() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final url = source.text.trim();
      if (url.isEmpty) {
        throw const FormatException('Enter a link or choose a torrent file.');
      }
      if (kind == 'Video') {
        await widget.client.rpc('add_video_task', {
          'url': url,
          'format_id': quality,
          if (filename.text.trim().isNotEmpty) 'filename': filename.text.trim(),
        });
      } else {
        if (url.toLowerCase().endsWith('.torrent') &&
            !url.startsWith('http://') &&
            !url.startsWith('https://') &&
            inspectedTorrent != url) {
          throw const FormatException(
            'Inspect the torrent before downloading.',
          );
        }
        if (torrentInfo != null &&
            !torrentPriorities.any((value) => value > 0)) {
          throw const FormatException('Select at least one torrent file.');
        }
        final parsedHeaders = headers.text.trim().isEmpty
            ? <String, dynamic>{}
            : jsonDecode(headers.text);
        if (parsedHeaders is! Map ||
            parsedHeaders.values.any((v) => v is! String)) {
          throw const FormatException(
            'Headers must be a JSON object with text values.',
          );
        }
        await widget.client.rpc('add_download', {
          'source': url,
          'headers': parsedHeaders,
          if (filename.text.trim().isNotEmpty) 'filename': filename.text.trim(),
          if (destination.text.trim().isNotEmpty)
            'dest_dir': destination.text.trim(),
          'mirrors': mirrors.text
              .split('\n')
              .map((s) => s.trim())
              .where((s) => s.isNotEmpty)
              .toList(),
          if (torrentInfo != null && inspectedTorrent == url)
            'file_priorities': torrentPriorities,
        });
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> inspectTorrent(String path) async {
    setState(() {
      busy = true;
      error = null;
      torrentInfo = null;
      torrentPriorities = [];
      source.text = path;
    });
    try {
      final result = await widget.client.rpc('inspect_torrent', {'path': path});
      final info = Map<String, dynamic>.from(result['torrent']);
      final files = info['files'] as List? ?? [];
      if (mounted) {
        setState(() {
          torrentInfo = info;
          inspectedTorrent = path;
          torrentPriorities = [
            for (final file in files)
              Map<String, dynamic>.from(file)['priority'] as int,
          ];
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('New download'),
    content: SizedBox(
      width: 510,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                  value: 'File',
                  label: Text('File / torrent'),
                  icon: Icon(Icons.link_rounded),
                ),
                ButtonSegment(
                  value: 'Video',
                  label: Text('Video / audio'),
                  icon: Icon(Icons.play_circle_outline),
                ),
              ],
              selected: {kind},
              onSelectionChanged: busy
                  ? null
                  : (v) => setState(() {
                      kind = v.first;
                      error = null;
                      videoTitle = null;
                    }),
            ),
            const SizedBox(height: 22),
            TextField(
              controller: source,
              autofocus: true,
              enabled: !busy,
              decoration: InputDecoration(
                labelText: kind == 'Video'
                    ? 'Video page URL'
                    : 'URL, magnet link or torrent path',
              ),
              onChanged: (value) => setState(() {
                videoTitle = null;
                if (value.trim() != inspectedTorrent) {
                  torrentInfo = null;
                  inspectedTorrent = null;
                  torrentPriorities = [];
                }
              }),
            ),
            if (kind == 'File')
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: busy
                      ? null
                      : () async {
                          final file = await openFile(
                            acceptedTypeGroups: [
                              const XTypeGroup(
                                label: 'Torrent',
                                extensions: ['torrent'],
                              ),
                            ],
                          );
                          if (file != null && mounted) {
                            await inspectTorrent(file.path);
                          }
                        },
                  icon: const Icon(Icons.folder_open_outlined, size: 18),
                  label: const Text('Choose torrent file'),
                ),
              ),
            if (kind == 'File' &&
                source.text.trim().toLowerCase().endsWith('.torrent') &&
                torrentInfo == null)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: busy
                      ? null
                      : () => inspectTorrent(source.text.trim()),
                  icon: const Icon(Icons.manage_search_rounded, size: 18),
                  label: const Text('Inspect torrent contents'),
                ),
              ),
            if (kind == 'File' && torrentInfo != null) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(
                    context,
                  ).colorScheme.surfaceContainerHighest.withValues(alpha: .45),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      torrentInfo!['name']?.toString() ?? 'Torrent contents',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${DownloadTask.formatBytes((torrentInfo!['total_size'] as num).round())} · '
                      'Seeds: ${torrentInfo!['seeds'] ?? '—'} · '
                      'Peers: ${torrentInfo!['peers'] ?? '—'}',
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      torrentInfo!['tracker_status']?.toString() ?? '',
                      style: TextStyle(
                        fontSize: 11,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    Row(
                      children: [
                        TextButton(
                          onPressed: () => setState(() {
                            final files = torrentInfo!['files'] as List;
                            torrentPriorities = [
                              for (final file in files)
                                Map<String, dynamic>.from(file)['pad'] == true
                                    ? 0
                                    : 4,
                            ];
                          }),
                          child: const Text('Select all'),
                        ),
                        TextButton(
                          onPressed: () => setState(() {
                            torrentPriorities = [
                              for (final _ in torrentPriorities) 0,
                            ];
                          }),
                          child: const Text('Select none'),
                        ),
                      ],
                    ),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxHeight: 230),
                      child: ListView.builder(
                        shrinkWrap: true,
                        itemCount: (torrentInfo!['files'] as List).length,
                        itemBuilder: (_, index) {
                          final file = Map<String, dynamic>.from(
                            (torrentInfo!['files'] as List)[index],
                          );
                          if (file['pad'] == true) {
                            return const SizedBox.shrink();
                          }
                          return Material(
                            color: Colors.transparent,
                            child: CheckboxListTile(
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              value: torrentPriorities[index] > 0,
                              onChanged: busy
                                  ? null
                                  : (selected) => setState(() {
                                      torrentPriorities[index] =
                                          selected == true ? 4 : 0;
                                    }),
                              title: Text(
                                file['name'].toString(),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              subtitle: Text(
                                DownloadTask.formatBytes(
                                  (file['size'] as num).round(),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ],
            if (kind == 'Video') ...[
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: quality,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Quality'),
                items: const [
                  DropdownMenuItem(
                    value: 'best',
                    child: Text('Best available video'),
                  ),
                  DropdownMenuItem(
                    value: 'worst',
                    child: Text('Smallest video'),
                  ),
                  DropdownMenuItem(
                    value: 'bestaudio',
                    child: Text('Audio only'),
                  ),
                ],
                onChanged: busy ? null : (v) => setState(() => quality = v!),
              ),
              TextButton(
                onPressed: busy
                    ? null
                    : () async {
                        setState(() {
                          busy = true;
                          error = null;
                        });
                        try {
                          final info = await widget.client.rpc(
                            'fetch_video_info',
                            {'url': source.text.trim()},
                          );
                          if (mounted) {
                            setState(() => videoTitle = info['title']);
                          }
                        } catch (e) {
                          if (mounted) setState(() => error = '$e');
                        } finally {
                          if (mounted) setState(() => busy = false);
                        }
                      },
                child: const Text('Check video title'),
              ),
              if (videoTitle != null) Text(videoTitle!),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: filename,
              enabled: !busy,
              decoration: const InputDecoration(
                labelText: 'Filename (optional)',
              ),
            ),
            if (kind == 'File')
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: const Text(
                  'Advanced options',
                  style: TextStyle(fontSize: 14),
                ),
                children: [
                  const SizedBox(height: 8),
                  TextField(
                    controller: destination,
                    enabled: !busy,
                    decoration: InputDecoration(
                      labelText: 'Save in (default if empty)',
                      suffixIcon: IconButton(
                        tooltip: 'Choose folder',
                        onPressed: busy
                            ? null
                            : () async {
                                final path = await getDirectoryPath();
                                if (path != null && mounted) {
                                  destination.text = path;
                                }
                              },
                        icon: const Icon(Icons.folder_open_outlined),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: headers,
                    enabled: !busy,
                    minLines: 2,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      labelText: 'HTTP headers (JSON)',
                      hintText: '{"Referer": "https://example.com"}',
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: mirrors,
                    enabled: !busy,
                    minLines: 2,
                    maxLines: 4,
                    decoration: const InputDecoration(
                      labelText: 'Mirror URLs (one per line)',
                      helperText:
                          'Mirrors must serve the same file. HTTP downloads only.',
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
              ),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: busy ? null : () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: busy ? null : submit,
        child: Text(busy ? 'Please wait…' : 'Download'),
      ),
    ],
  );
}

class PreferencesDialog extends StatefulWidget {
  const PreferencesDialog({super.key, required this.client, this.onAppearance});
  final IpcClient client;
  final VoidCallback? onAppearance;
  @override
  State<PreferencesDialog> createState() => _PreferencesDialogState();
}

class _PreferencesDialogState extends State<PreferencesDialog> {
  final path = TextEditingController(),
      concurrent = TextEditingController(),
      bandwidth = TextEditingController();
  final Map<String, TextEditingController> categories = {};
  bool loading = true,
      busy = false,
      schedule = false,
      metered = false,
      extract = true,
      startup = false,
      defender = true;
  int start = 2, end = 6;
  String? error;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final config = await widget.client.getConfig();
      final settings = await widget.client.getSettings();
      if (!mounted) return;
      path.text = config['download_dir'] ?? '';
      concurrent.text = '${config['max_concurrent_downloads'] ?? 3}';
      bandwidth.text = '${(config['global_bandwidth_limit'] ?? 0) / 1024}';
      schedule = config['scheduler_enabled'] ?? false;
      start = config['scheduler_start_hour'] ?? 2;
      end = config['scheduler_end_hour'] ?? 6;
      metered = config['pause_on_metered'] ?? false;
      extract = config['auto_extract'] ?? true;
      startup = settings['run_on_startup'] ?? false;
      defender = config['defender_scan_enabled'] ?? true;
      for (final cat in [
        'Video',
        'Music',
        'Programs',
        'Documents',
        'Compressed',
        'Photos',
        'Torrents',
        'Other',
      ]) {
        categories[cat] = TextEditingController(
          text: config['category_dirs']?[cat] ?? '',
        );
      }
      setState(() => loading = false);
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          loading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    for (final c in [path, concurrent, bandwidth, ...categories.values]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final count = int.tryParse(concurrent.text),
          rate = double.tryParse(bandwidth.text);
      if (count == null || count < 1 || count > 100) {
        throw const FormatException(
          'Concurrent downloads must be between 1 and 100.',
        );
      }
      if (rate == null || !rate.isFinite || rate < 0) {
        throw const FormatException('Enter a valid bandwidth limit.');
      }
      await widget.client.updateSettings({
        'download_dir': path.text.trim(),
        'max_concurrent_downloads': count,
        'global_bandwidth_limit': (rate * 1024).round(),
        'scheduler_enabled': schedule,
        'scheduler_start_hour': start,
        'scheduler_end_hour': end,
        'pause_on_metered': metered,
        'auto_extract': extract,
        'run_on_startup': startup,
        'defender_scan_enabled': defender,
        'category_dirs': {
          for (final entry in categories.entries)
            if (entry.value.text.trim().isNotEmpty)
              entry.key: entry.value.text.trim(),
        },
      });
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget directory(String label, TextEditingController controller) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: TextField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        suffixIcon: IconButton(
          tooltip: 'Choose folder',
          onPressed: () async {
            final dir = await getDirectoryPath();
            if (dir != null && mounted) controller.text = dir;
          },
          icon: const Icon(Icons.folder_open_outlined),
        ),
      ),
    ),
  );
  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Settings'),
    content: SizedBox(
      width: 560,
      child: loading
          ? const SizedBox(
              height: 180,
              child: Center(child: CircularProgressIndicator()),
            )
          : SingleChildScrollView(
              child: AbsorbPointer(
                absorbing: busy,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (widget.onAppearance != null)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.palette_outlined),
                        title: const Text('Appearance & color'),
                        subtitle: const Text(
                          'Accent color, theme, density and motion',
                        ),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: widget.onAppearance,
                      ),
                    directory('Download folder', path),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: concurrent,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Concurrent downloads',
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: TextField(
                            controller: bandwidth,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Limit (KB/s)',
                              helperText: '0 = unlimited',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Download on a schedule'),
                      subtitle: const Text('Uses your computer’s local time'),
                      value: schedule,
                      onChanged: (v) => setState(() => schedule = v),
                    ),
                    if (schedule)
                      Row(
                        children: [
                          for (final isStart in [true, false])
                            Expanded(
                              child: Padding(
                                padding: const EdgeInsets.only(right: 10),
                                child: DropdownButtonFormField<int>(
                                  isExpanded: true,
                                  initialValue: isStart ? start : end,
                                  decoration: InputDecoration(
                                    labelText: isStart ? 'Start' : 'End',
                                  ),
                                  items: [
                                    for (var h = 0; h < 24; h++)
                                      DropdownMenuItem(
                                        value: h,
                                        child: Text(
                                          '${h.toString().padLeft(2, '0')}:00',
                                        ),
                                      ),
                                  ],
                                  onChanged: (v) => setState(() {
                                    if (isStart) {
                                      start = v!;
                                    } else {
                                      end = v!;
                                    }
                                  }),
                                ),
                              ),
                            ),
                        ],
                      ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Pause on metered connections'),
                      value: metered,
                      onChanged: (v) => setState(() => metered = v),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Extract archives when finished'),
                      value: extract,
                      onChanged: (v) => setState(() => extract = v),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Run service at sign-in'),
                      value: startup,
                      onChanged: (v) => setState(() => startup = v),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('Scan completed files'),
                      subtitle: const Text(
                        'Uses Windows Defender and records a SHA-256 fingerprint',
                      ),
                      value: defender,
                      onChanged: (v) => setState(() => defender = v),
                    ),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Folders by file type'),
                      subtitle: const Text(
                        'Leave empty to use the default location',
                      ),
                      children: [
                        for (final entry in categories.entries)
                          directory(entry.key, entry.value),
                      ],
                    ),
                    const ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: Text('Browser integration'),
                      children: [
                        Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: SelectableText(
                            'Install the extension from this project’s browser_extension folder using your browser’s Load unpacked option. Register the native host with its extension ID using native_host/register_native_host.py. Captured downloads will appear in this library.',
                          ),
                        ),
                      ],
                    ),
                    if (error != null)
                      Text(
                        error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                  ],
                ),
              ),
            ),
    ),
    actions: [
      TextButton(
        onPressed: busy ? null : () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: loading || busy || categories.isEmpty ? null : save,
        child: Text(busy ? 'Saving…' : 'Save changes'),
      ),
    ],
  );
}

class DownloadDetails extends StatefulWidget {
  const DownloadDetails({super.key, required this.client, required this.task});
  final IpcClient client;
  final DownloadTask task;
  @override
  State<DownloadDetails> createState() => _DownloadDetailsState();
}

class _DownloadDetailsState extends State<DownloadDetails> {
  Map<String, dynamic>? details;
  String? error;
  bool busy = false;
  late int priority = widget.task.priority ?? 1;
  List<int> filePriorities = [];
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final result = await widget.client.rpc('task_details', {
        'task_id': widget.task.id,
      });
      if (mounted) {
        setState(() {
          details = Map<String, dynamic>.from(result['task']);
          filePriorities = [
            for (final f in details!['files'] ?? []) f['priority'] as int,
          ];
          error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.client.setPriority(widget.task.id, priority);
      if (filePriorities.isNotEmpty) {
        await widget.client.rpc('set_file_priorities', {
          'task_id': widget.task.id,
          'priorities': filePriorities,
        });
      }
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = details;
    return AlertDialog(
      title: const Text('Download details'),
      content: SizedBox(
        width: 540,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                widget.task.title,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 18,
                ),
              ),
              const SizedBox(height: 18),
              if (d == null && error == null) const LinearProgressIndicator(),
              if (d != null) ...[
                for (final entry in {
                  'Source': d['source'],
                  'Saved to': widget.task.filePath,
                  'Type': d['type'],
                  'Created': DateTime.fromMillisecondsSinceEpoch(
                    ((d['created_at'] as num) * 1000).round(),
                  ).toLocal().toString().split('.').first,
                  if (d['type'] == 'http') 'Connections': d['num_connections'],
                  if (d['type'] == 'http')
                    'Resumable': d['supports_ranges'] == true
                        ? 'Yes'
                        : 'Not reported by server',
                  if (d['type'] == 'torrent')
                    'Peers / seeds': '${d['num_peers']} / ${d['num_seeds']}',
                  if ((d['mirrors'] as List? ?? []).isNotEmpty)
                    'Mirrors': (d['mirrors'] as List).join('\n'),
                  if ((d['description'] ?? '').toString().isNotEmpty)
                    'Description': d['description'],
                }.entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.key,
                          style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(
                              context,
                            ).colorScheme.onSurfaceVariant,
                          ),
                        ),
                        const SizedBox(height: 4),
                        SelectableText('${entry.value ?? ''}'),
                      ],
                    ),
                  ),
                if (d['health'] is Map && (d['health'] as Map).isNotEmpty)
                  _DetailsPanel(
                    title: 'Download health',
                    icon: Icons.monitor_heart_outlined,
                    values: {
                      'Connection': d['health']['state'],
                      'Acceleration':
                          d['health']['acceleration'] ??
                          'Waiting for server probe',
                      'Final host': d['health']['final_host'] ?? '—',
                      'HTTP status': d['health']['response_status'] ?? '—',
                      'Range resume': d['health']['supports_ranges'] == true
                          ? 'Available'
                          : 'Unavailable',
                      'Connections':
                          d['health']['effective_connections'] ??
                          d['health']['requested_connections'] ??
                          '—',
                      'Validator': d['health']['validator'] ?? '—',
                      'Browser cookies':
                          d['health']['cookies_forwarded'] == true
                          ? 'Forwarded'
                          : 'Not supplied',
                      'Browser referrer':
                          d['health']['referrer_forwarded'] == true
                          ? 'Forwarded'
                          : 'Not supplied',
                      if ((d['health']['failure_reason'] ?? '')
                          .toString()
                          .isNotEmpty)
                        'Why it failed': d['health']['failure_reason'],
                    },
                  ),
                if (d['safety'] is Map)
                  _DetailsPanel(
                    title: 'Safety',
                    icon: Icons.shield_outlined,
                    values: {
                      'Status': d['safety']['status'] ?? 'pending',
                      'Windows Defender': d['safety']['defender'] ?? 'pending',
                      if ((d['safety']['signature']?['status'] ?? '')
                          .toString()
                          .isNotEmpty)
                        'Publisher signature':
                            d['safety']['signature']['status'],
                      if ((d['safety']['signature']?['signer'] ?? '')
                          .toString()
                          .isNotEmpty)
                        'Publisher': d['safety']['signature']['signer'],
                      if ((d['safety']['sha256'] ?? '').toString().isNotEmpty)
                        'SHA-256': d['safety']['sha256'],
                      if ((d['safety']['warnings'] as List? ?? []).isNotEmpty)
                        'Warnings': (d['safety']['warnings'] as List).join(
                          '\n',
                        ),
                    },
                    action: widget.task.status == TaskStatus.completed
                        ? TextButton.icon(
                            onPressed: busy
                                ? null
                                : () async {
                                    setState(() => busy = true);
                                    try {
                                      await widget.client.rpc('rescan_task', {
                                        'task_id': widget.task.id,
                                      });
                                      await Future<void>.delayed(
                                        const Duration(milliseconds: 250),
                                      );
                                      await load();
                                    } catch (e) {
                                      if (mounted) setState(() => error = '$e');
                                    } finally {
                                      if (mounted) setState(() => busy = false);
                                    }
                                  },
                            icon: const Icon(Icons.refresh_rounded),
                            label: const Text('Scan again'),
                          )
                        : null,
                  ),
              ],
              DropdownButtonFormField<int>(
                isExpanded: true,
                initialValue: priority,
                decoration: const InputDecoration(labelText: 'Priority'),
                items: const [
                  DropdownMenuItem(
                    value: 0,
                    child: Text(
                      'Low · 1 MB/s background mode',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem(value: 1, child: Text('Normal')),
                  DropdownMenuItem(value: 2, child: Text('High')),
                ],
                onChanged: busy ? null : (v) => setState(() => priority = v!),
              ),
              const SizedBox(height: 8),
              const Text(
                'Low priority limits active downloads immediately. Connection changes apply on the next start.',
                style: TextStyle(fontSize: 12),
              ),
              if (d?['type'] == 'torrent') ...[
                const SizedBox(height: 18),
                const Text(
                  'Torrent files',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                if (filePriorities.isEmpty)
                  TextButton(
                    onPressed: load,
                    child: const Text('Metadata unavailable · Refresh'),
                  ),
                for (var i = 0; i < filePriorities.length; i++)
                  if (d!['files'][i]['pad'] != true)
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(d['files'][i]['name']),
                      subtitle: Text(
                        DownloadTask.formatBytes(d['files'][i]['size']),
                      ),
                      value: filePriorities[i] > 0,
                      onChanged: busy
                          ? null
                          : (v) =>
                                setState(() => filePriorities[i] = v! ? 4 : 0),
                    ),
              ],
              if (error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 16),
                  child: Text(
                    error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: busy ? null : () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        FilledButton(onPressed: busy ? null : save, child: const Text('Apply')),
      ],
    );
  }
}

class _DetailsPanel extends StatelessWidget {
  const _DetailsPanel({
    required this.title,
    required this.icon,
    required this.values,
    this.action,
  });
  final String title;
  final IconData icon;
  final Map<String, dynamic> values;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: 18),
    padding: const EdgeInsets.all(14),
    decoration: BoxDecoration(
      color: Theme.of(
        context,
      ).colorScheme.surfaceContainerHighest.withValues(alpha: .45),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            ?action,
          ],
        ),
        const SizedBox(height: 10),
        for (final entry in values.entries)
          Padding(
            padding: const EdgeInsets.only(bottom: 7),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 130,
                  child: Text(
                    entry.key,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                      fontSize: 12,
                    ),
                  ),
                ),
                Expanded(child: SelectableText('${entry.value}')),
              ],
            ),
          ),
      ],
    ),
  );
}

class AppearanceDialog extends StatefulWidget {
  const AppearanceDialog({
    super.key,
    required this.mode,
    required this.compactRows,
    required this.reduceMotion,
    required this.onModeChanged,
    required this.onCompactRowsChanged,
    required this.onReduceMotionChanged,
    this.accent = AccentColor.pink,
    this.onAccentChanged,
  });

  final ThemeMode mode;
  final bool compactRows;
  final bool reduceMotion;
  final ValueChanged<ThemeMode> onModeChanged;
  final ValueChanged<bool> onCompactRowsChanged;
  final ValueChanged<bool> onReduceMotionChanged;
  final AccentColor accent;
  final ValueChanged<AccentColor>? onAccentChanged;

  @override
  State<AppearanceDialog> createState() => _AppearanceDialogState();
}

class _AppearanceDialogState extends State<AppearanceDialog> {
  late ThemeMode mode = widget.mode;
  late bool compactRows = widget.compactRows;
  late bool reduceMotion = widget.reduceMotion;
  late AccentColor accent = widget.accent;

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Appearance'),
    content: SizedBox(
      width: 440,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Theme', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final value in ThemeMode.values)
                  ChoiceChip(
                    label: Text(
                      value.name[0].toUpperCase() + value.name.substring(1),
                    ),
                    selected: mode == value,
                    onSelected: (_) => setState(() => mode = value),
                  ),
              ],
            ),
            const SizedBox(height: 18),
            const Text(
              'Accent color',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final value in AccentColor.values)
                  ChoiceChip(
                    label: Text(value.label),
                    avatar: CircleAvatar(
                      backgroundColor:
                          Theme.of(context).brightness == Brightness.dark
                          ? value.dark
                          : value.light,
                      radius: 7,
                    ),
                    selected: accent == value,
                    onSelected: (_) => setState(() => accent = value),
                  ),
              ],
            ),
            const SizedBox(height: 18),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Compact download rows'),
              subtitle: const Text('Fits more downloads on screen'),
              value: compactRows,
              onChanged: (value) => setState(() => compactRows = value),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Reduce motion'),
              subtitle: const Text('Minimizes interface animations'),
              value: reduceMotion,
              onChanged: (value) => setState(() => reduceMotion = value),
            ),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancel'),
      ),
      FilledButton(
        onPressed: () {
          widget.onModeChanged(mode);
          widget.onAccentChanged?.call(accent);
          widget.onCompactRowsChanged(compactRows);
          widget.onReduceMotionChanged(reduceMotion);
          Navigator.pop(context);
        },
        child: const Text('Save'),
      ),
    ],
  );
}

class UpdateDialog extends StatefulWidget {
  const UpdateDialog({super.key, required this.client});
  final IpcClient client;

  @override
  State<UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<UpdateDialog> {
  Map<String, dynamic>? update;
  Map<String, dynamic>? package;
  String? error;
  bool busy = false;

  @override
  void initState() {
    super.initState();
    check();
  }

  Future<void> check() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final result = await widget.client.rpc('check_for_updates');
      if (mounted) {
        setState(() => update = Map<String, dynamic>.from(result['update']));
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> download() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final result = await widget.client.rpc('download_update');
      if (mounted) {
        setState(() => package = Map<String, dynamic>.from(result['package']));
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> install() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await widget.client.rpc('install_update', {'path': package!['path']});
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          busy = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final available = update?['available'] == true;
    return AlertDialog(
      title: const Text('Software updates'),
      content: SizedBox(
        width: 500,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Installed version ${update?['current_version'] ?? '…'}'),
            const SizedBox(height: 12),
            if (busy) const LinearProgressIndicator(),
            if (!busy && update != null)
              Text(
                available
                    ? 'Version ${update!['version']} is available.'
                    : 'You are using the latest stable version.',
              ),
            if (available && update?['ready'] != true)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  'This release is missing its installer or SHA-256 manifest.',
                ),
              ),
            if (package != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  'Verified publisher: ${package!['signature']['signer']}',
                ),
              ),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            const SizedBox(height: 12),
            const Text(
              'Updates install only after SHA-256 verification and a valid trusted Windows publisher signature.',
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: busy ? null : () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        if (update == null || !available)
          TextButton(
            onPressed: busy ? null : check,
            child: const Text('Check again'),
          ),
        if (available && package == null)
          FilledButton(
            onPressed: busy || update?['ready'] != true ? null : download,
            child: const Text('Download and verify'),
          ),
        if (package != null)
          FilledButton(
            onPressed: busy ? null : install,
            child: const Text('Install update'),
          ),
      ],
    );
  }
}

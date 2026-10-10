import 'package:flutter/material.dart';
import 'package:file_selector/file_selector.dart';
import '../services/ipc_client.dart';
import '../theme/app_theme.dart';

class SettingsDialog extends StatefulWidget {
  const SettingsDialog({super.key});

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  final _ipcClient = IpcClient();
  bool _isLoading = true;
  String _downloadDir = '';
  double _maxConcurrent = 3;
  double _maxBandwidth = 0;
  bool _schedulerEnabled = false;
  double _schedulerStartHour = 2;
  double _schedulerEndHour = 6;
  bool _autoExtract = true;
  bool _pauseOnMetered = false;
  Map<String, String> _categoryDirs = {};

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final config = await _ipcClient.getConfig();
      setState(() {
        _downloadDir = config['download_dir'] ?? '';
        _maxConcurrent = (config['max_concurrent_downloads'] ?? 3).toDouble();
        _maxBandwidth = ((config['global_bandwidth_limit'] ?? 0) / 1024)
            .toDouble();
        _schedulerEnabled = config['scheduler_enabled'] ?? false;
        _schedulerStartHour = (config['scheduler_start_hour'] ?? 2).toDouble();
        _schedulerEndHour = (config['scheduler_end_hour'] ?? 6).toDouble();
        _autoExtract = config['auto_extract'] ?? true;
        _pauseOnMetered = config['pause_on_metered'] ?? false;

        final cats = config['category_dirs'];
        if (cats != null && cats is Map) {
          _categoryDirs = Map<String, String>.from(cats);
        } else {
          _categoryDirs = {};
        }

        _isLoading = false;
      });
    } catch (e) {
      debugPrint("Failed to load settings: $e");
      if (mounted) {
        Navigator.pop(context);
      }
    }
  }

  Future<void> _saveSettings() async {
    try {
      await _ipcClient.setConfig({
        'download_dir': _downloadDir,
        'category_dirs': _categoryDirs,
        'max_concurrent_downloads': _maxConcurrent.toInt(),
        'global_bandwidth_limit': (_maxBandwidth * 1024).toInt(),
        'scheduler_enabled': _schedulerEnabled,
        'scheduler_start_hour': _schedulerStartHour.toInt(),
        'scheduler_end_hour': _schedulerEndHour.toInt(),
        'auto_extract': _autoExtract,
        'pause_on_metered': _pauseOnMetered,
      });
      if (mounted) {
        Navigator.pop(context);
      }
    } catch (e) {
      debugPrint("Failed to save settings: $e");
    }
  }

  Future<void> _pickDirectory() async {
    final String? directoryPath = await getDirectoryPath();
    if (directoryPath != null) {
      setState(() {
        _downloadDir = directoryPath;
      });
    }
  }

  Future<void> _pickCategoryDirectory(String category) async {
    final String? directoryPath = await getDirectoryPath();
    if (directoryPath != null) {
      setState(() {
        _categoryDirs[category] = directoryPath;
      });
    }
  }

  void _clearCategoryDirectory(String category) {
    setState(() {
      _categoryDirs.remove(category);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      child: ClipRRect(
        borderRadius: AppRadius.lg,
        child: Container(
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.9),
            border: Border.all(color: AppColors.border),
            borderRadius: AppRadius.lg,
          ),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    'Settings',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 24),

                  // Download Directory
                  Text(
                    'Download Directory',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          _downloadDir.isEmpty ? 'Not set' : _downloadDir,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(color: AppColors.textMuted),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      TextButton(
                        onPressed: _pickDirectory,
                        child: const Text('Change'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Category Directories
                  Theme(
                    data: Theme.of(
                      context,
                    ).copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                      title: Text(
                        'Category Directories (Optional)',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      tilePadding: EdgeInsets.zero,
                      children:
                          [
                            'Programs',
                            'Video',
                            'Music',
                            'Documents',
                            'Compressed',
                            'Photos',
                            'Torrents',
                            'Other',
                          ].map((category) {
                            final path = _categoryDirs[category];
                            return Padding(
                              padding: const EdgeInsets.only(
                                bottom: 8.0,
                                left: 16.0,
                              ),
                              child: Row(
                                children: [
                                  SizedBox(
                                    width: 100,
                                    child: Text(
                                      category,
                                      style: Theme.of(
                                        context,
                                      ).textTheme.bodyMedium,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      (path == null || path.isEmpty)
                                          ? 'Default'
                                          : path,
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: AppColors.textMuted,
                                          ),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  if (path != null && path.isNotEmpty)
                                    IconButton(
                                      icon: const Icon(Icons.clear, size: 16),
                                      onPressed: () =>
                                          _clearCategoryDirectory(category),
                                      padding: EdgeInsets.zero,
                                      constraints: const BoxConstraints(),
                                    ),
                                  TextButton(
                                    onPressed: () =>
                                        _pickCategoryDirectory(category),
                                    child: const Text('Change'),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Max Concurrent Downloads
                  Text(
                    'Max Concurrent Downloads: ${_maxConcurrent.toInt()}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  Slider(
                    value: _maxConcurrent,
                    min: 1,
                    max: 10,
                    divisions: 9,
                    onChanged: (val) {
                      setState(() {
                        _maxConcurrent = val;
                      });
                    },
                  ),
                  const SizedBox(height: 16),

                  // Max Bandwidth
                  Text(
                    'Max Bandwidth: ${_maxBandwidth == 0 ? 'Unlimited' : '${_maxBandwidth.toInt()} KB/s'}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  Slider(
                    value: _maxBandwidth,
                    min: 0,
                    max: 10000, // up to 10MB/s for slider
                    divisions: 100,
                    onChanged: (val) {
                      setState(() {
                        _maxBandwidth = val;
                      });
                    },
                  ),
                  const SizedBox(height: 16),

                  // Scheduler Window
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Scheduler Enabled',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      Switch(
                        value: _schedulerEnabled,
                        onChanged: (val) {
                          setState(() {
                            _schedulerEnabled = val;
                          });
                        },
                      ),
                    ],
                  ),
                  if (_schedulerEnabled) ...[
                    const SizedBox(height: 8),
                    Text(
                      'Start Hour: ${_schedulerStartHour.toInt()}:00',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    Slider(
                      value: _schedulerStartHour,
                      min: 0,
                      max: 23,
                      divisions: 23,
                      onChanged: (val) =>
                          setState(() => _schedulerStartHour = val),
                    ),
                    Text(
                      'End Hour: ${_schedulerEndHour.toInt()}:00',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    Slider(
                      value: _schedulerEndHour,
                      min: 0,
                      max: 23,
                      divisions: 23,
                      onChanged: (val) =>
                          setState(() => _schedulerEndHour = val),
                    ),
                  ],
                  const SizedBox(height: 16),

                  // Auto Extract
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Auto Extract ZIPs',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      Switch(
                        value: _autoExtract,
                        onChanged: (val) {
                          setState(() {
                            _autoExtract = val;
                          });
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),

                  // Pause on metered
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Pause on Metered Network',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      Switch(
                        value: _pauseOnMetered,
                        onChanged: (val) {
                          setState(() {
                            _pauseOnMetered = val;
                          });
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),

                  // Actions
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('Cancel'),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton(
                        onPressed: _saveSettings,
                        child: const Text('Save'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

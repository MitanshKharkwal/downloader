import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

import '../theme/app_theme.dart';

enum TaskCategory { video, music, programs, documents, compressed, photos, other }

extension TaskCategoryX on TaskCategory {
  String get label {
    switch (this) {
      case TaskCategory.video:
        return 'Video';
      case TaskCategory.music:
        return 'Music';
      case TaskCategory.programs:
        return 'Programs';
      case TaskCategory.documents:
        return 'Documents';
      case TaskCategory.compressed:
        return 'Compressed';
      case TaskCategory.photos:
        return 'Photos';
      case TaskCategory.other:
        return 'Other';
    }
  }

  IconData get icon {
    switch (this) {
      case TaskCategory.video:
        return PhosphorIcons.videoCamera(PhosphorIconsStyle.light);
      case TaskCategory.music:
        return PhosphorIcons.musicNote(PhosphorIconsStyle.light);
      case TaskCategory.programs:
        return PhosphorIcons.terminal(PhosphorIconsStyle.light);
      case TaskCategory.documents:
        return PhosphorIcons.fileText(PhosphorIconsStyle.light);
      case TaskCategory.compressed:
        return PhosphorIcons.archive(PhosphorIconsStyle.light);
      case TaskCategory.photos:
        return PhosphorIcons.image(PhosphorIconsStyle.light);
      case TaskCategory.other:
        return PhosphorIcons.file(PhosphorIconsStyle.light);
    }
  }
}

enum TaskStatus { downloading, paused, completed, error, queued, canceled }

extension TaskStatusX on TaskStatus {
  String get label {
    switch (this) {
      case TaskStatus.downloading:
        return 'Downloading';
      case TaskStatus.paused:
        return 'Paused';
      case TaskStatus.completed:
        return 'Completed';
      case TaskStatus.error:
        return 'Failed';
      case TaskStatus.queued:
        return 'Queued';
      case TaskStatus.canceled:
        return 'Canceled';
    }
  }

  Color get color {
    switch (this) {
      case TaskStatus.downloading:
        return AppColors.accent;
      case TaskStatus.paused:
        return AppColors.textMuted;
      case TaskStatus.completed:
        return AppColors.success;
      case TaskStatus.error:
        return AppColors.danger;
      case TaskStatus.queued:
        return AppColors.warning;
      case TaskStatus.canceled:
        return AppColors.textMuted;
    }
  }

  bool get isActive => this == TaskStatus.downloading;
}

/// A single download. Mutable so the ticking simulation can advance it in place.
class DownloadTask {
  DownloadTask({
    required this.id,
    required this.title,
    required this.category,
    required this.sizeBytes,
    required this.progress,
    required this.speedBytesPerSec,
    required this.status,
    this.errorMessage,
    this.priority,
  });

  factory DownloadTask.fromJson(Map<String, dynamic> json) {
    TaskCategory category = TaskCategory.other;
    final catStr = json['category']?.toString().toLowerCase() ?? '';
    if (catStr.contains('video')) category = TaskCategory.video;
    else if (catStr.contains('music') || catStr.contains('audio')) category = TaskCategory.music;
    else if (catStr.contains('program') || catStr.contains('exe')) category = TaskCategory.programs;
    else if (catStr.contains('compressed') || catStr.contains('zip')) category = TaskCategory.compressed;
    else if (catStr.contains('photo') || catStr.contains('image')) category = TaskCategory.photos;
    else if (catStr.contains('document') || catStr.contains('pdf')) category = TaskCategory.documents;

    TaskStatus status = TaskStatus.queued;
    final statStr = json['status']?.toString().toUpperCase() ?? '';
    if (statStr == 'DOWNLOADING') status = TaskStatus.downloading;
    else if (statStr == 'PAUSED') status = TaskStatus.paused;
    else if (statStr == 'COMPLETED') status = TaskStatus.completed;
    else if (statStr == 'ERROR') status = TaskStatus.error;
    else if (statStr == 'CANCELED') status = TaskStatus.canceled;

    final totalBytes = json['total_bytes'] ?? 0;
    final downloadedBytes = json['downloaded_bytes'] ?? 0;
    double progress = 0.0;
    if (totalBytes > 0) {
      progress = (downloadedBytes / totalBytes).clamp(0.0, 1.0);
    } else if (status == TaskStatus.completed) {
      progress = 1.0;
    }

    return DownloadTask(
      id: json['id'] ?? '',
      title: _extractFilename(json['file_path']) ?? json['source'] ?? 'Unknown Source',
      category: category,
      sizeBytes: totalBytes,
      progress: progress,
      speedBytesPerSec: (json['speed_bps'] ?? 0.0).toDouble(),
      status: status,
      errorMessage: json['error_message'] ?? json['error'],
      priority: json['priority'],
    );
  }

  static String? _extractFilename(String? path) {
    if (path == null || path.isEmpty) return null;
    final segments = path.replaceAll('\\', '/').split('/');
    if (segments.isEmpty) return null;
    return segments.last;
  }


  final String id;
  final String title;
  final TaskCategory category;
  final int sizeBytes;

  /// 0.0 - 1.0
  double progress;
  double speedBytesPerSec;
  TaskStatus status;
  String? errorMessage;
  int? priority;

  int get downloadedBytes => (sizeBytes * progress).round();
  int get remainingBytes => (sizeBytes - downloadedBytes).clamp(0, sizeBytes);

  /// Seconds remaining, or null when it cannot be estimated.
  int? get etaSeconds {
    if (!status.isActive || speedBytesPerSec <= 0) return null;
    return (remainingBytes / speedBytesPerSec).round();
  }

  String get sizeLabel => formatBytes(sizeBytes);

  String get speedLabel =>
      status.isActive ? '${formatBytes(speedBytesPerSec.round())}/s' : '—';

  String get etaLabel {
    if (status == TaskStatus.completed) return 'Done';
    if (status == TaskStatus.error) return 'Failed';
    if (status == TaskStatus.canceled) return 'Canceled';
    if (status == TaskStatus.paused) return 'Paused';
    if (status == TaskStatus.queued) return 'Queued';
    final int? eta = etaSeconds;
    if (eta == null) return '—';
    return formatDuration(eta);
  }

  static String formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    const List<String> units = <String>['KB', 'MB', 'GB', 'TB'];
    double value = bytes / 1024;
    int unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit++;
    }
    final String formatted =
        value >= 100 ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
    return '$formatted ${units[unit]}';
  }

  static String formatDuration(int seconds) {
    if (seconds <= 0) return '0s';
    if (seconds < 60) return '${seconds}s';
    final int minutes = seconds ~/ 60;
    if (minutes < 60) {
      final int rest = seconds % 60;
      return rest == 0 ? '${minutes}m' : '${minutes}m ${rest}s';
    }
    final int hours = minutes ~/ 60;
    final int restMinutes = minutes % 60;
    return restMinutes == 0 ? '${hours}h' : '${hours}h ${restMinutes}m';
  }
}

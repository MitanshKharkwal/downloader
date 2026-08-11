class DownloadTask {
  final String id;
  final String source;
  final String status;
  final int priority;
  final int downloadedBytes;
  final int totalBytes;
  final double speedBps;
  final String filePath;
  final String error;
  final String category;
  final double createdAt;
  final String description;

  DownloadTask({
    required this.id,
    required this.source,
    required this.status,
    required this.priority,
    required this.downloadedBytes,
    required this.totalBytes,
    required this.speedBps,
    required this.filePath,
    required this.error,
    required this.category,
    required this.createdAt,
    required this.description,
  });

  factory DownloadTask.fromJson(Map<String, dynamic> json) {
    return DownloadTask(
      id: json['id'] ?? '',
      source: json['source'] ?? '',
      status: json['status'] ?? 'UNKNOWN',
      priority: json['priority'] is int ? json['priority'] : int.tryParse(json['priority']?.toString() ?? '1') ?? 1,
      downloadedBytes: json['downloaded_bytes'] ?? 0,
      totalBytes: json['total_bytes'] ?? 0,
      speedBps: (json['speed_bps'] ?? 0.0).toDouble(),
      filePath: json['file_path'] ?? '',
      error: json['error'] ?? '',
      category: json['category'] ?? 'Uncategorized',
      createdAt: (json['created_at'] ?? 0.0).toDouble(),
      description: json['description'] ?? '',
    );
  }
}

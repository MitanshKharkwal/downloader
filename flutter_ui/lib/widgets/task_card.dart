import 'package:flutter/material.dart';
import 'package:flutter_ui/models/download_task.dart';

class TaskCard extends StatelessWidget {
  final DownloadTask task;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onCancel;

  const TaskCard({
    Key? key,
    required this.task,
    required this.onPause,
    required this.onResume,
    required this.onCancel,
  }) : super(key: key);

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  }

  String _formatSpeed(double bps) {
    return '${_formatBytes(bps.toInt())}/s';
  }

  @override
  Widget build(BuildContext context) {
    final progress = task.totalBytes > 0 ? task.downloadedBytes / task.totalBytes : 0.0;
    final filename = task.filePath.isNotEmpty 
        ? task.filePath.split('\\').last.split('/').last 
        : task.source.split('/').last;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      color: const Color(0xFF232533),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    filename,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _getStatusColor(task.status).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    task.status,
                    style: TextStyle(color: _getStatusColor(task.status), fontSize: 12, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: progress,
                backgroundColor: Colors.white12,
                valueColor: AlwaysStoppedAnimation<Color>(_getStatusColor(task.status)),
                minHeight: 8,
              ),
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${_formatBytes(task.downloadedBytes)} / ${_formatBytes(task.totalBytes)}',
                      style: const TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      task.status == 'DOWNLOADING' ? _formatSpeed(task.speedBps) : '--',
                      style: const TextStyle(color: Colors.tealAccent, fontSize: 12),
                    ),
                  ],
                ),
                Row(
                  children: [
                    if (task.status == 'DOWNLOADING')
                      IconButton(
                        icon: const Icon(Icons.pause, color: Colors.orangeAccent),
                        onPressed: onPause,
                      )
                    else if (task.status == 'PAUSED' || task.status == 'ERROR')
                      IconButton(
                        icon: const Icon(Icons.play_arrow, color: Colors.greenAccent),
                        onPressed: onResume,
                      ),
                    IconButton(
                      icon: const Icon(Icons.cancel, color: Colors.redAccent),
                      onPressed: onCancel,
                    ),
                  ],
                )
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'DOWNLOADING': return Colors.blueAccent;
      case 'PAUSED': return Colors.orangeAccent;
      case 'COMPLETED': return Colors.greenAccent;
      case 'ERROR': return Colors.redAccent;
      default: return Colors.grey;
    }
  }
}

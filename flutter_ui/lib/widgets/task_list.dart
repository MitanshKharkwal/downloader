import 'package:flutter/material.dart';

import '../models/download_task.dart';
import '../theme/app_theme.dart';
import 'task_card.dart';

class TaskList extends StatelessWidget {
  const TaskList({
    super.key,
    required this.tasks,
    required this.onPause,
    required this.onResume,
    required this.onRetry,
    required this.onCancel,
    required this.compact,
  });

  final List<DownloadTask> tasks;
  final ValueChanged<DownloadTask> onPause;
  final ValueChanged<DownloadTask> onResume;
  final ValueChanged<DownloadTask> onRetry;
  final ValueChanged<DownloadTask> onCancel;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: tasks.length,
      padding: const EdgeInsets.fromLTRB(28, 4, 28, 28),
      itemBuilder: (BuildContext context, int index) {
        final DownloadTask task = tasks[index];
        return TaskCard(
          key: ValueKey<String>(task.id),
          task: task,
          compact: compact,
          onPause: () => onPause(task),
          onResume: () => onResume(task),
          onRetry: () => onRetry(task),
          onCancel: () => onCancel(task),
        );
      },
    );
  }
}

/// Column headers above the list, matching the card's right-hand stat columns.
class TaskListHeader extends StatelessWidget {
  const TaskListHeader({super.key, required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final TextStyle? style =
        Theme.of(context).textTheme.labelSmall?.copyWith(
              color: AppColors.textMuted,
              fontSize: 10,
              letterSpacing: 0.9,
            );

    return Padding(
      padding: const EdgeInsets.fromLTRB(42, 0, 42, 10),
      child: Row(
        children: <Widget>[
          Expanded(child: Text('NAME', style: style)),
          SizedBox(
            width: 68,
            child: Text('SIZE', textAlign: TextAlign.right, style: style),
          ),
          if (!compact) ...<Widget>[
            SizedBox(
              width: 84,
              child: Text('SPEED', textAlign: TextAlign.right, style: style),
            ),
            SizedBox(
              width: 72,
              child: Text('ETA', textAlign: TextAlign.right, style: style),
            ),
          ],
          const SizedBox(width: 80),
        ],
      ),
    );
  }
}

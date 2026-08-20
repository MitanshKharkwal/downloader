import 'package:flutter/material.dart';

import '../models/download_task.dart';
import '../theme/app_theme.dart';

class TaskCard extends StatefulWidget {
  const TaskCard({
    super.key,
    required this.task,
    required this.onPause,
    required this.onResume,
    required this.onRetry,
    required this.onCancel,
    this.compact = false,
  });

  final DownloadTask task;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onRetry;
  final VoidCallback onCancel;

  /// Hides speed/ETA columns on narrow widths.
  final bool compact;

  @override
  State<TaskCard> createState() => _TaskCardState();
}

class _TaskCardState extends State<TaskCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final DownloadTask task = widget.task;
    final TextTheme text = Theme.of(context).textTheme;
    final bool dimmed =
        task.status == TaskStatus.paused || task.status == TaskStatus.queued;
    final bool isError = task.status == TaskStatus.error;
    final bool isDone = task.status == TaskStatus.completed;

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: AnimatedContainer(
        duration: AppTheme.fast,
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: isError
              ? Color.alphaBlend(AppColors.dangerSoft, AppColors.surface)
              : _hovered
                  ? AppColors.surfaceHover
                  : AppColors.surface,
          borderRadius: AppRadius.md,
          border: Border.all(
            color: isError
                ? AppColors.danger.withValues(alpha: 0.45)
                : _hovered
                    ? AppColors.borderStrong
                    : AppColors.border,
          ),
        ),
        child: AnimatedOpacity(
          duration: AppTheme.fast,
          opacity: dimmed ? 0.55 : 1,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              _FileIcon(task: task),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Flexible(
                          child: Text(
                            task.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: text.bodyMedium?.copyWith(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textPrimary,
                            ),
                          ),
                        ),
                        if (isDone) ...<Widget>[
                          const SizedBox(width: 8),
                          const Icon(
                            Icons.check_circle_rounded,
                            size: 15,
                            color: AppColors.success,
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 7),
                    if (isDone)
                      Text(
                        '${task.sizeLabel} · Completed',
                        style: text.labelSmall?.copyWith(
                          color: AppColors.textMuted,
                          fontSize: 11,
                        ),
                      )
                    else if (isError)
                      Text(
                        task.errorMessage ?? 'Download failed',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: text.labelSmall?.copyWith(
                          color: AppColors.danger,
                          fontSize: 11,
                        ),
                      )
                    else
                      Row(
                        children: <Widget>[
                          Expanded(child: _ProgressBar(task: task)),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: 34,
                            child: Text(
                              '${(task.progress * 100).round()}%',
                              textAlign: TextAlign.right,
                              style: text.labelSmall?.copyWith(
                                color: AppColors.textMuted,
                                fontSize: 11,
                                fontFeatures: const <FontFeature>[
                                  FontFeature.tabularFigures(),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              _Stats(task: task, compact: widget.compact),
              const SizedBox(width: 8),
              _Actions(
                task: task,
                visible: _hovered,
                onPause: widget.onPause,
                onResume: widget.onResume,
                onRetry: widget.onRetry,
                onCancel: widget.onCancel,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FileIcon extends StatelessWidget {
  const _FileIcon({required this.task});

  final DownloadTask task;

  @override
  Widget build(BuildContext context) {
    final Color tint = task.status == TaskStatus.error
        ? AppColors.danger
        : task.status == TaskStatus.completed
            ? AppColors.success
            : AppColors.accent;

    return Container(
      height: 38,
      width: 38,
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.12),
        borderRadius: AppRadius.sm,
        border: Border.all(color: tint.withValues(alpha: 0.22)),
      ),
      child: Icon(task.category.icon, size: 18, color: tint),
    );
  }
}

class _ProgressBar extends StatelessWidget {
  const _ProgressBar({required this.task});

  final DownloadTask task;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: AppRadius.pill,
      child: SizedBox(
        height: 3,
        child: Stack(
          children: <Widget>[
            const ColoredBox(color: AppColors.track),
            AnimatedFractionallySizedBox(
              duration: AppTheme.medium,
              curve: Curves.easeOut,
              widthFactor: task.progress.clamp(0.0, 1.0),
              alignment: Alignment.centerLeft,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: AppRadius.pill,
                  color: task.status.color,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Stats extends StatelessWidget {
  const _Stats({required this.task, required this.compact});

  final DownloadTask task;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;

    TextStyle? style(Color color) => text.labelSmall?.copyWith(
          color: color,
          fontSize: 11.5,
          fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
        );

    return Row(
      children: <Widget>[
        SizedBox(
          width: 68,
          child: Text(
            task.sizeLabel,
            textAlign: TextAlign.right,
            style: style(AppColors.textSecondary),
          ),
        ),
        if (!compact) ...<Widget>[
          SizedBox(
            width: 84,
            child: Text(
              task.speedLabel,
              textAlign: TextAlign.right,
              style: style(
                task.status.isActive
                    ? AppColors.textPrimary
                    : AppColors.textMuted,
              ),
            ),
          ),
          SizedBox(
            width: 72,
            child: Text(
              task.etaLabel,
              textAlign: TextAlign.right,
              style: style(AppColors.textMuted),
            ),
          ),
        ],
      ],
    );
  }
}

class _Actions extends StatelessWidget {
  const _Actions({
    required this.task,
    required this.visible,
    required this.onPause,
    required this.onResume,
    required this.onRetry,
    required this.onCancel,
  });

  final DownloadTask task;
  final bool visible;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onRetry;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final List<Widget> buttons = <Widget>[];

    switch (task.status) {
      case TaskStatus.downloading:
        buttons.add(
          _IconAction(icon: Icons.pause_rounded, tip: 'Pause', onTap: onPause),
        );
        break;
      case TaskStatus.paused:
      case TaskStatus.queued:
        buttons.add(
          _IconAction(
            icon: Icons.play_arrow_rounded,
            tip: 'Resume',
            onTap: onResume,
          ),
        );
        break;
      case TaskStatus.error:
        buttons.add(
          _IconAction(
            icon: Icons.refresh_rounded,
            tip: 'Retry',
            onTap: onRetry,
            color: AppColors.danger,
          ),
        );
        break;
      case TaskStatus.completed:
        buttons.add(
          _IconAction(
            icon: Icons.folder_open_rounded,
            tip: 'Show in folder',
            onTap: () {},
          ),
        );
        break;
    }

    buttons.add(
      _IconAction(
        icon: Icons.close_rounded,
        tip: task.status == TaskStatus.completed ? 'Remove' : 'Cancel',
        onTap: onCancel,
      ),
    );

    return SizedBox(
      width: 72,
      child: AnimatedOpacity(
        duration: AppTheme.fast,
        opacity: visible ? 1 : 0,
        child: IgnorePointer(
          ignoring: !visible,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: buttons,
          ),
        ),
      ),
    );
  }
}

class _IconAction extends StatefulWidget {
  const _IconAction({
    required this.icon,
    required this.tip,
    required this.onTap,
    this.color,
  });

  final IconData icon;
  final String tip;
  final VoidCallback onTap;
  final Color? color;

  @override
  State<_IconAction> createState() => _IconActionState();
}

class _IconActionState extends State<_IconAction> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final Color fg = widget.color ??
        (_hovered ? AppColors.textPrimary : AppColors.textSecondary);

    return Padding(
      padding: const EdgeInsets.only(left: 4),
      child: Tooltip(
        message: widget.tip,
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          onEnter: (_) => setState(() => _hovered = true),
          onExit: (_) => setState(() => _hovered = false),
          child: GestureDetector(
            onTap: widget.onTap,
            child: AnimatedContainer(
              duration: AppTheme.fast,
              height: 28,
              width: 28,
              decoration: BoxDecoration(
                color: _hovered ? AppColors.surfaceActive : Colors.transparent,
                borderRadius: AppRadius.sm,
                border: Border.all(
                  color: _hovered ? AppColors.borderStrong : Colors.transparent,
                ),
              ),
              child: Icon(widget.icon, size: 15, color: fg),
            ),
          ),
        ),
      ),
    );
  }
}

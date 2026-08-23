import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

import 'speed_sparkline.dart';

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
    required this.onRemove,
    required this.onPriority,
    this.compact = false,
  });

  final DownloadTask task;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onRetry;
  final VoidCallback onCancel;
  final VoidCallback onRemove;
  final ValueChanged<int> onPriority;

  /// Hides speed/ETA columns on narrow widths.
  final bool compact;

  @override
  State<TaskCard> createState() => _TaskCardState();
}

class _TaskCardState extends State<TaskCard> with SingleTickerProviderStateMixin {
  bool _hovered = false;
  late final AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 250),
    );
  }

  @override
  void didUpdateWidget(TaskCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.task.status != TaskStatus.completed && widget.task.status == TaskStatus.completed) {
      _pulseController.forward(from: 0.0).then((_) {
        if (mounted) _pulseController.reverse();
      });
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

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
          child: ScaleTransition(
            scale: Tween<double>(begin: 1.0, end: 1.04).animate(
              CurvedAnimation(parent: _pulseController, curve: Curves.easeOutCubic),
            ),
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
                          Icon(
                            PhosphorIcons.checkCircle(PhosphorIconsStyle.fill),
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
                          const Spacer(),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: 34,
                            child: TweenAnimationBuilder<double>(
                              tween: Tween<double>(begin: task.progress, end: task.progress),
                              duration: const Duration(milliseconds: 750),
                              curve: Curves.easeOut,
                              builder: (BuildContext context, double val, Widget? child) {
                                return Text(
                                  '${(val * 100).round()}%',
                                  textAlign: TextAlign.right,
                                  style: text.labelSmall?.copyWith(
                                    color: AppColors.textMuted,
                                    fontSize: 11,
                                    fontFeatures: const <FontFeature>[
                                      FontFeature.tabularFigures(),
                                    ],
                                  ),
                                );
                              },
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
                onRemove: widget.onRemove,
                onPriority: widget.onPriority,
              ),
            ],
          ),
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

    return Stack(
      alignment: Alignment.center,
      children: <Widget>[
        if (task.status.isActive || task.status == TaskStatus.paused || task.progress > 0)
          SizedBox(
            width: 44,
            height: 44,
            child: TweenAnimationBuilder<double>(
              tween: Tween<double>(begin: task.progress, end: task.progress),
              duration: const Duration(milliseconds: 950),
              curve: Curves.easeInOutCubic,
              builder: (BuildContext context, double value, _) {
                return CircularProgressIndicator(
                  value: value.clamp(0.0, 1.0),
                  strokeWidth: 2.5,
                  backgroundColor: Colors.transparent,
                  color: task.status.color,
                );
              },
            ),
          ),
        Container(
          height: 38,
          width: 38,
          decoration: BoxDecoration(
            color: tint.withValues(alpha: 0.12),
            borderRadius: AppRadius.sm,
            border: Border.all(color: tint.withValues(alpha: 0.22)),
          ),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 250),
            transitionBuilder: (Widget child, Animation<double> animation) {
              return FadeTransition(
                opacity: animation,
                child: ScaleTransition(
                  scale: Tween<double>(begin: 0.8, end: 1.0).animate(animation),
                  child: child,
                ),
              );
            },
            child: Icon(task.category.icon, key: ValueKey<TaskStatus>(task.status), size: 18, color: tint),
          ),
        ),
      ],
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
          if (task.status.isActive) ...<Widget>[
            SpeedSparkline(speedBytesPerSec: task.speedBytesPerSec, active: task.status.isActive),
            const SizedBox(width: 8),
          ],
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
    required this.onRemove,
    required this.onPriority,
  });

  final DownloadTask task;
  final bool visible;
  final VoidCallback onPause;
  final VoidCallback onResume;
  final VoidCallback onRetry;
  final VoidCallback onCancel;
  final VoidCallback onRemove;
  final ValueChanged<int> onPriority;

  @override
  Widget build(BuildContext context) {
    final List<Widget> buttons = <Widget>[];

    switch (task.status) {
      case TaskStatus.downloading:
        buttons.add(
          _PlayPauseAction(
            isPlaying: true,
            tip: 'Pause',
            onTap: onPause,
          ),
        );
        break;
      case TaskStatus.paused:
      case TaskStatus.queued:
        buttons.add(
          _PlayPauseAction(
            isPlaying: false,
            tip: 'Resume',
            onTap: onResume,
          ),
        );
        break;
      case TaskStatus.error:
        buttons.add(
          _IconAction(
            icon: PhosphorIcons.arrowsClockwise(PhosphorIconsStyle.light),
            tip: 'Retry',
            onTap: onRetry,
            color: AppColors.danger,
          ),
        );
        break;
      case TaskStatus.completed:
        buttons.add(
          _IconAction(
            icon: PhosphorIcons.folderOpen(PhosphorIconsStyle.light),
            tip: 'Show in folder',
            onTap: () {},
          ),
        );
        break;
      case TaskStatus.canceled:
        break;
    }

    if (task.status == TaskStatus.queued || task.status == TaskStatus.downloading) {
      IconData pIcon = PhosphorIcons.arrowsDownUp(PhosphorIconsStyle.light);
      if (task.priority == 2) pIcon = PhosphorIcons.caretDoubleUp(PhosphorIconsStyle.light);
      if (task.priority == 0) pIcon = PhosphorIcons.caretDoubleDown(PhosphorIconsStyle.light);

      buttons.add(
        PopupMenuButton<int>(
          initialValue: task.priority ?? 1,
          tooltip: 'Set Priority',
          onSelected: onPriority,
          offset: const Offset(0, 32),
          child: _IconAction(
            icon: pIcon,
            tip: 'Priority',
            onTap: () {},
          ),
          itemBuilder: (BuildContext context) => <PopupMenuEntry<int>>[
            const PopupMenuItem<int>(
              value: 2,
              child: Text('High Priority'),
            ),
            const PopupMenuItem<int>(
              value: 1,
              child: Text('Normal Priority'),
            ),
            const PopupMenuItem<int>(
              value: 0,
              child: Text('Low Priority'),
            ),
          ],
        ),
      );
    }

    buttons.add(
      _IconAction(
        icon: PhosphorIcons.x(PhosphorIconsStyle.light),
        tip: (task.status == TaskStatus.completed || task.status == TaskStatus.canceled) ? 'Remove' : 'Cancel',
        onTap: (task.status == TaskStatus.completed || task.status == TaskStatus.canceled) ? onRemove : onCancel,
      ),
    );

    return SizedBox(
      width: 104,
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
  bool _pressed = false;

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
            onTapDown: (_) => setState(() => _pressed = true),
            onTapUp: (_) => setState(() => _pressed = false),
            onTapCancel: () => setState(() => _pressed = false),
            onTap: widget.onTap,
            child: AnimatedScale(
              scale: _pressed ? 0.92 : 1.0,
              duration: Duration(milliseconds: _pressed ? 90 : 120),
              curve: Curves.easeOut,
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
      ),
    );
  }
}

class _PlayPauseAction extends StatefulWidget {
  const _PlayPauseAction({
    required this.isPlaying,
    required this.tip,
    required this.onTap,
  });

  final bool isPlaying;
  final String tip;
  final VoidCallback onTap;

  @override
  State<_PlayPauseAction> createState() => _PlayPauseActionState();
}

class _PlayPauseActionState extends State<_PlayPauseAction> with SingleTickerProviderStateMixin {
  bool _hovered = false;
  bool _pressed = false;
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
      value: widget.isPlaying ? 1.0 : 0.0,
    );
  }

  @override
  void didUpdateWidget(_PlayPauseAction oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isPlaying != widget.isPlaying) {
      if (widget.isPlaying) {
        _controller.forward();
      } else {
        _controller.reverse();
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Color fg = _hovered ? AppColors.textPrimary : AppColors.textSecondary;

    return Padding(
      padding: const EdgeInsets.only(left: 4),
      child: Tooltip(
        message: widget.tip,
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          onEnter: (_) => setState(() => _hovered = true),
          onExit: (_) => setState(() => _hovered = false),
          child: GestureDetector(
            onTapDown: (_) => setState(() => _pressed = true),
            onTapUp: (_) => setState(() => _pressed = false),
            onTapCancel: () => setState(() => _pressed = false),
            onTap: widget.onTap,
            child: AnimatedScale(
              scale: _pressed ? 0.92 : 1.0,
              duration: Duration(milliseconds: _pressed ? 90 : 120),
              curve: Curves.easeOut,
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
                child: AnimatedIcon(
                  icon: AnimatedIcons.play_pause,
                  progress: _controller,
                  size: 15,
                  color: fg,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

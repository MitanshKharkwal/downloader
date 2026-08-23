import 'package:flutter/material.dart';

import '../models/download_task.dart';
import '../theme/app_theme.dart';
import 'task_card.dart';

class TaskList extends StatefulWidget {
  const TaskList({
    super.key,
    required this.tasks,
    required this.onPause,
    required this.onResume,
    required this.onRetry,
    required this.onCancel,
    required this.onRemove,
    required this.onPriority,
    required this.compact,
  });

  final List<DownloadTask> tasks;
  final ValueChanged<DownloadTask> onPause;
  final ValueChanged<DownloadTask> onResume;
  final ValueChanged<DownloadTask> onRetry;
  final ValueChanged<DownloadTask> onCancel;
  final ValueChanged<DownloadTask> onRemove;
  final void Function(DownloadTask, int) onPriority;
  final bool compact;

  @override
  State<TaskList> createState() => _TaskListState();
}

class _TaskListState extends State<TaskList> {
  final GlobalKey<AnimatedListState> _listKey = GlobalKey<AnimatedListState>();
  late List<DownloadTask> _items;
  bool _didInitialBuild = false;

  @override
  void initState() {
    super.initState();
    _items = List.from(widget.tasks);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _didInitialBuild = true;
    });
  }

  @override
  void didUpdateWidget(TaskList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_didInitialBuild) {
      _syncList(oldWidget.tasks, widget.tasks);
    } else {
      _items = List.from(widget.tasks);
    }
  }

  void _syncList(List<DownloadTask> oldList, List<DownloadTask> newList) {
    final Set<String> newIds = newList.map((t) => t.id).toSet();

    for (int i = _items.length - 1; i >= 0; i--) {
      if (!newIds.contains(_items[i].id)) {
        final DownloadTask removedItem = _items.removeAt(i);
        _listKey.currentState?.removeItem(
          i,
          (BuildContext context, Animation<double> animation) =>
              _buildItem(removedItem, animation, isRemoving: true),
          duration: const Duration(milliseconds: 200),
        );
      }
    }

    for (int i = 0; i < newList.length; i++) {
      final DownloadTask task = newList[i];
      if (i >= _items.length || _items[i].id != task.id) {
        _items.insert(i, task);
        _listKey.currentState?.insertItem(i, duration: const Duration(milliseconds: 220));
      } else {
        _items[i] = task;
      }
    }
  }

  Widget _buildItem(DownloadTask task, Animation<double> animation, {bool isRemoving = false, int index = 0}) {
    final Widget child = TaskCard(
      key: ValueKey<String>(task.id),
      task: task,
      compact: widget.compact,
      onPause: () => widget.onPause(task),
      onResume: () => widget.onResume(task),
      onRetry: () => widget.onRetry(task),
      onCancel: () => widget.onCancel(task),
      onRemove: () => widget.onRemove(task),
      onPriority: (int p) => widget.onPriority(task, p),
    );

    if (isRemoving) {
      return SizeTransition(
        sizeFactor: animation,
        child: FadeTransition(
          opacity: animation,
          child: child,
        ),
      );
    }

    final CurvedAnimation curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
    final Widget animatedChild = FadeTransition(
      opacity: curved,
      child: SlideTransition(
        position: Tween<Offset>(begin: const Offset(0, 0.2), end: Offset.zero).animate(curved),
        child: child,
      ),
    );

    if (!_didInitialBuild && animation.isCompleted) {
      final int delay = (index * 35).clamp(0, 400);
      return _StaggeredEntrance(delay: delay, child: child);
    }

    return animatedChild;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedList(
      key: _listKey,
      initialItemCount: _items.length,
      padding: const EdgeInsets.fromLTRB(28, 4, 28, 28),
      itemBuilder: (BuildContext context, int index, Animation<double> animation) {
        return _buildItem(_items[index], animation, index: index);
      },
    );
  }
}

class _StaggeredEntrance extends StatefulWidget {
  const _StaggeredEntrance({required this.delay, required this.child});

  final int delay;
  final Widget child;

  @override
  State<_StaggeredEntrance> createState() => _StaggeredEntranceState();
}

class _StaggeredEntranceState extends State<_StaggeredEntrance> {
  double _val = 0.0;

  @override
  void initState() {
    super.initState();
    if (widget.delay == 0) {
      _val = 1.0;
    } else {
      Future.delayed(Duration(milliseconds: widget.delay), () {
        if (mounted) {
          setState(() => _val = 1.0);
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.delay == 0) return widget.child;
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0.0, end: _val),
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOutCubic,
      builder: (BuildContext context, double val, Widget? child) {
        return Opacity(
          opacity: val,
          child: Transform.translate(
            offset: Offset(0, 8 * (1 - val)),
            child: child,
          ),
        );
      },
      child: widget.child,
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

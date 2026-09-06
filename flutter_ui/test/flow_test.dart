import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_ui/models/download_task.dart';
import 'package:flutter_ui/theme/app_theme.dart';
import 'package:flutter_ui/widgets/add_url_dialog.dart';
import 'package:flutter_ui/widgets/task_card.dart';

/// Helper: wrap a widget with MaterialApp + dark theme.
Widget _wrap(Widget child) {
  return MaterialApp(
    theme: AppTheme.dark(),
    home: Scaffold(body: Center(child: SizedBox(width: 900, child: child))),
  );
}

/// A minimal [DownloadTask] for testing.
DownloadTask _task({
  String id = 'test-1',
  TaskStatus status = TaskStatus.downloading,
  double progress = 0.5,
}) {
  return DownloadTask(
    id: id,
    title: 'test_file.zip',
    category: TaskCategory.compressed,
    sizeBytes: 1024 * 1024,
    progress: progress,
    speedBytesPerSec: 512 * 1024,
    status: status,
  );
}

void main() {
  // ──────────────────────────────────────────────────────────────────
  // Flow 1: Add a Download
  // ──────────────────────────────────────────────────────────────────

  group('Flow 1 — AddUrlDialog', () {
    testWidgets('Add button disabled when text field is empty', (tester) async {
      await tester.pumpWidget(_wrap(
        AddUrlDialog(onAdd: (_) async {}),
      ));
      await tester.pumpAndSettle();

      final addButton = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Add Task'),
      );
      expect(addButton.onPressed, isNull,
          reason: 'Add button must be disabled when input is empty');
    });

    testWidgets('Add button disabled for non-URL text', (tester) async {
      await tester.pumpWidget(_wrap(
        AddUrlDialog(onAdd: (_) async {}),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'not a url');
      await tester.pump();

      final addButton = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Add Task'),
      );
      expect(addButton.onPressed, isNull,
          reason: 'Add button must be disabled for invalid URL');
    });

    testWidgets('Add button enabled for valid http URL', (tester) async {
      await tester.pumpWidget(_wrap(
        AddUrlDialog(onAdd: (_) async {}),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'http://example.com/file.zip');
      await tester.pump();

      final addButton = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Add Task'),
      );
      expect(addButton.onPressed, isNotNull,
          reason: 'Add button must be enabled for valid http:// URL');
    });

    testWidgets('Add button enabled for magnet link', (tester) async {
      await tester.pumpWidget(_wrap(
        AddUrlDialog(onAdd: (_) async {}),
      ));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'magnet:?xt=urn:btih:abc123');
      await tester.pump();

      final addButton = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Add Task'),
      );
      expect(addButton.onPressed, isNotNull,
          reason: 'Add button must be enabled for magnet: link');
    });

    testWidgets('Dialog stays open and shows error on failed submit', (tester) async {
      await tester.pumpWidget(MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body: Builder(builder: (ctx) {
            return ElevatedButton(
              onPressed: () => showDialog(
                context: ctx,
                builder: (_) => AddUrlDialog(
                  onAdd: (_) async => throw Exception('Unreachable host'),
                ),
              ),
              child: const Text('Open'),
            );
          }),
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'http://example.com/file.zip');
      await tester.pump();
      await tester.tap(find.widgetWithText(ElevatedButton, 'Add Task'));
      await tester.pumpAndSettle();

      // Dialog must still be visible
      expect(find.byType(AlertDialog), findsOneWidget,
          reason: 'Dialog must stay open when RPC fails');
      // Error message must be shown
      expect(find.textContaining('Unreachable host'), findsOneWidget,
          reason: 'Error message must appear inline in the dialog');
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // Flow 3: Pause / Resume
  // ──────────────────────────────────────────────────────────────────

  group('Flow 3 — Pause / Resume', () {
    testWidgets('Paused progress ring has distinct visual (lower opacity) vs downloading', (tester) async {
      // Both tasks have same progress, but paused must look different.
      // We verify via the Opacity widget that wraps the CircularProgressIndicator for paused.
      await tester.pumpWidget(_wrap(
        Column(
          children: [
            TaskCard(
              task: _task(id: 'a', status: TaskStatus.downloading),
              onPause: () {},
              onResume: () {},
              onRetry: () {},
              onCancel: () {},
              onRemove: () {},
              onPriority: (_) {},
            ),
            TaskCard(
              task: _task(id: 'b', status: TaskStatus.paused),
              onPause: () {},
              onResume: () {},
              onRetry: () {},
              onCancel: () {},
              onRemove: () {},
              onPriority: (_) {},
            ),
          ],
        ),
      ));
      await tester.pumpAndSettle();

      // Both cards render — the paused one has an Opacity widget wrapping the progress ring
      // with opacity 0.35 (we check via the Opacity widgets in the tree).
      final opacityWidgets = tester
          .widgetList<Opacity>(find.byType(Opacity))
          .where((o) => o.opacity == 0.35)
          .toList();
      expect(opacityWidgets.length, greaterThanOrEqualTo(1),
          reason: 'Paused progress ring must have reduced opacity (0.35) vs downloading');
    });

    testWidgets('Pause callback fires on action tap (via ActionsWidget direct)', (tester) async {
      bool pauseCalled = false;

      await tester.pumpWidget(_wrap(
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ActionsWidget(
              task: _task(status: TaskStatus.downloading),
              displayStatus: TaskStatus.downloading,
              visible: true,
              onPause: () => pauseCalled = true,
              onResume: () {},
              onRetry: () {},
              onCancel: () {},
              onRemove: () {},
              onPriority: (_) {},
            ),
          ],
        ),
      ));
      await tester.pumpAndSettle();

      // Tap the AnimatedIcon (play/pause icon)
      final icons = find.byType(AnimatedIcon);
      expect(icons, findsWidgets, reason: 'AnimatedIcon (play/pause) must be visible');
      await tester.tap(icons.first, warnIfMissed: false);
      await tester.pump();

      expect(pauseCalled, isTrue, reason: 'onPause callback must be called on tap');
    });

    testWidgets('Rapid double-tap does not fire pause callback twice (debounce)', (tester) async {
      int pauseCount = 0;

      await tester.pumpWidget(_wrap(
        TaskCard(
          task: _task(status: TaskStatus.downloading),
          onPause: () => pauseCount++,
          onResume: () {},
          onRetry: () {},
          onCancel: () {},
          onRemove: () {},
          onPriority: (_) {},
        ),
      ));
      await tester.pumpAndSettle();

      final gesture = await tester.createGesture();
      await gesture.addPointer();
      await gesture.moveTo(tester.getCenter(find.byType(TaskCard)));
      await tester.pump();

      final icons = find.byType(AnimatedIcon);
      if (icons.evaluate().isNotEmpty) {
        await tester.tap(icons.first, warnIfMissed: false);
        await tester.pump(const Duration(milliseconds: 50));
        await tester.tap(icons.first, warnIfMissed: false);
        await tester.pump();
      }

      expect(pauseCount, lessThanOrEqualTo(1),
          reason: 'Debounce must prevent duplicate calls on rapid double-tap');
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // Flow 4: Cancel
  // ──────────────────────────────────────────────────────────────────

  group('Flow 4 — Cancel', () {
    testWidgets('Cancel flow — _ActionsState state machine: confirming fires onCancel', (tester) async {
      bool cancelCalled = false;
      // Directly test _Actions widget in isolation, visible=true so no hover needed
      await tester.pumpWidget(_wrap(
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ActionsWidget(
              task: _task(status: TaskStatus.downloading),
              displayStatus: TaskStatus.downloading,
              visible: true,
              onPause: () {},
              onResume: () {},
              onRetry: () {},
              onCancel: () => cancelCalled = true,
              onRemove: () {},
              onPriority: (_) {},
            ),
          ],
        ),
      ));
      await tester.pumpAndSettle();

      // Tap X (Cancel) — should show confirm row, NOT fire cancelCalled
      await tester.tap(find.byTooltip('Cancel'), warnIfMissed: false);
      await tester.pump();

      expect(cancelCalled, isFalse,
          reason: 'Cancel must NOT fire immediately — confirmation required');
      expect(find.text('Cancel download?'), findsOneWidget,
          reason: 'Confirm row must appear after tapping Cancel');

      // Now confirm
      await tester.tap(find.text('Yes'));
      await tester.pump();

      expect(cancelCalled, isTrue,
          reason: 'onCancel must fire after confirming');
    });

    testWidgets('Dismissing cancel confirm does not call onCancel', (tester) async {
      bool cancelCalled = false;
      await tester.pumpWidget(_wrap(
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ActionsWidget(
              task: _task(status: TaskStatus.downloading),
              displayStatus: TaskStatus.downloading,
              visible: true,
              onPause: () {},
              onResume: () {},
              onRetry: () {},
              onCancel: () => cancelCalled = true,
              onRemove: () {},
              onPriority: (_) {},
            ),
          ],
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Cancel'), warnIfMissed: false);
      await tester.pump();
      expect(find.text('Cancel download?'), findsOneWidget);

      // Tap No
      await tester.tap(find.text('No'));
      await tester.pumpAndSettle();

      expect(cancelCalled, isFalse, reason: 'Dismissing confirm must not cancel');
      expect(find.text('Cancel download?'), findsNothing,
          reason: 'Confirm row must disappear after dismissal');
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // Flow 5: Completion + Remove
  // ──────────────────────────────────────────────────────────────────

  group('Flow 5 — Completion + Remove', () {
    testWidgets('Completed task shows "Completed" label', (tester) async {
      await tester.pumpWidget(_wrap(
        TaskCard(
          task: _task(status: TaskStatus.completed, progress: 1.0),
          onPause: () {},
          onResume: () {},
          onRetry: () {},
          onCancel: () {},
          onRemove: () {},
          onPriority: (_) {},
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.textContaining('Completed'), findsOneWidget,
          reason: 'Completed status must be clearly labeled');
    });

    testWidgets('Remove on completed calls onRemove without confirm dialog', (tester) async {
      bool removeCalled = false;

      await tester.pumpWidget(_wrap(
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ActionsWidget(
              task: _task(status: TaskStatus.completed, progress: 1.0),
              displayStatus: TaskStatus.completed,
              visible: true,
              onPause: () {},
              onResume: () {},
              onRetry: () {},
              onCancel: () {},
              onRemove: () => removeCalled = true,
              onPriority: (_) {},
            ),
          ],
        ),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Remove'), warnIfMissed: false);
      await tester.pump();

      expect(find.text('Cancel download?'), findsNothing,
          reason: 'No confirmation for removing completed task');
      expect(removeCalled, isTrue,
          reason: 'onRemove fires immediately for completed tasks');
    });

    testWidgets('All 6 task statuses have distinct colors', (tester) async {
      final statuses = TaskStatus.values;
      final colors = statuses.map((s) => s.color.toARGB32()).toList();
      final uniqueColors = colors.toSet();

      // The spec requires all 6 to be visually distinguishable.
      // paused=textMuted, canceled=textSecondary must differ.
      expect(TaskStatus.paused.color, isNot(equals(TaskStatus.canceled.color)),
          reason: 'paused and canceled must have distinct colors');

      expect(uniqueColors.length, equals(statuses.length),
          reason: 'All 6 task statuses must have unique colors');
    });
  });
}





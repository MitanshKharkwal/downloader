import 'package:flutter/material.dart';
import 'package:phosphor_icons/phosphor_icons.dart';

import '../theme/app_theme.dart';

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.title,
    required this.subtitle,
    this.icon,
    this.onAction,
    this.actionLabel,
  });

  final String title;
  final String subtitle;
  final IconData? icon;
  final VoidCallback? onAction;
  final String? actionLabel;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 320),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Container(
              height: 56,
              width: 56,
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.md,
              ),
              child: Icon(
                icon ?? PhosphorIcons.tray(PhosphorIconsStyle.light),
                size: 24,
                color: AppColors.textMuted,
              ),
            ),
            const SizedBox(height: 18),
            Text(
              title,
              textAlign: TextAlign.center,
              style: text.titleMedium?.copyWith(fontSize: 15, color: AppColors.textPrimary),
            ),
            const SizedBox(height: 6),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: text.bodySmall?.copyWith(color: AppColors.textMuted, height: 1.5),
            ),
            if (onAction != null && actionLabel != null) ...<Widget>[
              const SizedBox(height: 16),
              _TextAction(label: actionLabel!, onPressed: onAction!),
            ],
          ],
        ),
      ),
    );
  }
}

class _TextAction extends StatefulWidget {
  const _TextAction({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  State<_TextAction> createState() => _TextActionState();
}

class _TextActionState extends State<_TextAction> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.onPressed,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              PhosphorIcons.plus(PhosphorIconsStyle.light),
              size: 14,
              color: _hovered ? AppColors.accentHover : AppColors.accent,
            ),
            const SizedBox(width: 5),
            Text(
              widget.label,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w500,
                color: _hovered ? AppColors.accentHover : AppColors.accent,
              ),
            ),
          ],
        ),
      ),
    );
  }
}


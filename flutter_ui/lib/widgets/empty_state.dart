import 'package:flutter/material.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

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

    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0.0, end: 1.0),
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
      builder: (BuildContext context, double val, Widget? child) {
        return Opacity(
          opacity: val,
          child: Transform.scale(
            scale: 0.97 + (0.03 * val),
            child: child,
          ),
        );
      },
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Container(
                height: 92,
                width: 92,
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: AppRadius.lg,
                  border: Border.all(color: AppColors.border),
                ),
                child: Icon(icon ?? PhosphorIcons.tray(PhosphorIconsStyle.light), size: 40, color: AppColors.textMuted),
              ),
              const SizedBox(height: 22),
              Text(
                title,
                textAlign: TextAlign.center,
                style: text.titleMedium?.copyWith(
                  fontSize: 17,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: text.bodySmall?.copyWith(
                  color: AppColors.textMuted,
                  height: 1.5,
                ),
              ),
              if (onAction != null && actionLabel != null) ...<Widget>[
                const SizedBox(height: 20),
                _GhostButton(label: actionLabel!, onPressed: onAction!),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _GhostButton extends StatefulWidget {
  const _GhostButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  State<_GhostButton> createState() => _GhostButtonState();
}

class _GhostButtonState extends State<_GhostButton> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.onPressed,
        child: AnimatedContainer(
          duration: AppTheme.fast,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: _hovered ? AppColors.accent : AppColors.accentSoft,
            borderRadius: AppRadius.md,
            border: Border.all(
              color: _hovered ? AppColors.accent : AppColors.borderStrong,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                PhosphorIcons.plus(PhosphorIconsStyle.light),
                size: 16,
                color: _hovered ? Colors.white : AppColors.textPrimary,
              ),
              const SizedBox(width: 8),
              Text(
                widget.label,
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: _hovered ? Colors.white : AppColors.textPrimary,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

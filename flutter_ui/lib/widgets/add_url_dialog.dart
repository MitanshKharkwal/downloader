import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class AddUrlDialog extends StatefulWidget {
  final Future<void> Function(String) onAdd;

  const AddUrlDialog({super.key, required this.onAdd});

  @override
  State<AddUrlDialog> createState() => _AddUrlDialogState();
}

class _AddUrlDialogState extends State<AddUrlDialog> {
  final _controller = TextEditingController();
  bool _isButtonEnabled = false;
  bool _isLoading = false;
  String? _errorMessage;

  static bool _isValidInput(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return false;
    if (trimmed.startsWith('magnet:?')) return true;
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return true;
    }
    return false;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final url = _controller.text.trim();
    if (!_isValidInput(url) || _isLoading) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      await widget.onAdd(url);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = e.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;

    return AlertDialog(
      backgroundColor: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.lg,
        side: const BorderSide(color: AppColors.border),
      ),
      title: const Text('Add New Download', style: TextStyle(color: AppColors.textPrimary)),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _controller,
              autofocus: true,
              enabled: !_isLoading,
              style: text.bodyMedium?.copyWith(color: AppColors.textPrimary),
              decoration: InputDecoration(
                hintText: 'Paste URL or magnet linkâ€¦',
                hintStyle: const TextStyle(color: AppColors.textMuted),
                filled: true,
                fillColor: AppColors.background,
                border: OutlineInputBorder(
                  borderRadius: AppRadius.md,
                  borderSide: BorderSide(
                    color: _errorMessage != null ? AppColors.danger : AppColors.border,
                  ),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: AppRadius.md,
                  borderSide: BorderSide(
                    color: _errorMessage != null ? AppColors.danger : AppColors.border,
                  ),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: AppRadius.md,
                  borderSide: BorderSide(
                    color: _errorMessage != null ? AppColors.danger : AppColors.accent,
                    width: 1.5,
                  ),
                ),
              ),
              onChanged: (value) {
                final enabled = _isValidInput(value);
                if (enabled != _isButtonEnabled || _errorMessage != null) {
                  setState(() {
                    _isButtonEnabled = enabled;
                    _errorMessage = null;
                  });
                }
              },
              onSubmitted: (_) => _isButtonEnabled ? _submit() : null,
            ),
            // Inline error row â€” dialog stays open on failure, user keeps their typed URL
            AnimatedSize(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOut,
              child: _errorMessage != null
                  ? Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        decoration: BoxDecoration(
                          color: AppColors.dangerSoft,
                          borderRadius: AppRadius.sm,
                          border: Border.all(color: AppColors.danger.withValues(alpha: 0.3)),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.error_outline, size: 14, color: AppColors.danger),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                _errorMessage!,
                                style: text.labelSmall?.copyWith(
                                  color: AppColors.danger,
                                  fontSize: 11.5,
                                  height: 1.4,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _isLoading ? null : () => Navigator.pop(context),
          child: Text(
            'Cancel',
            style: TextStyle(color: _isLoading ? AppColors.textMuted : AppColors.textSecondary),
          ),
        ),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 150),
          child: _isLoading
              ? SizedBox(
                  key: const ValueKey('loading'),
                  height: 36,
                  width: 100,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.accent,
                      shape: RoundedRectangleBorder(borderRadius: AppRadius.md),
                    ),
                    onPressed: null,
                    child: const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    ),
                  ),
                )
              : SizedBox(
                  key: const ValueKey('submit'),
                  height: 36,
                  width: 100,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: _isButtonEnabled
                          ? AppColors.accent
                          : AppColors.surfaceActive,
                      shape: RoundedRectangleBorder(borderRadius: AppRadius.md),
                    ),
                    onPressed: _isButtonEnabled ? _submit : null,
                    child: Text(
                      'Add Task',
                      style: TextStyle(
                        color: _isButtonEnabled ? AppColors.textPrimary : AppColors.textMuted,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

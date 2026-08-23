import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class AddUrlDialog extends StatefulWidget {
  final Function(String) onAdd;

  const AddUrlDialog({super.key, required this.onAdd});

  @override
  State<AddUrlDialog> createState() => _AddUrlDialogState();
}

class _AddUrlDialogState extends State<AddUrlDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.surface,
      title: const Text('Add New Download', style: TextStyle(color: AppColors.textPrimary)),
      content: TextField(
        controller: _controller,
        style: const TextStyle(color: AppColors.textPrimary),
        decoration: InputDecoration(
          hintText: 'Enter URL...',
          hintStyle: const TextStyle(color: AppColors.textMuted),
          filled: true,
          fillColor: AppColors.background,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel', style: TextStyle(color: AppColors.textSecondary)),
        ),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.accent,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
          onPressed: () {
            final trimmedText = _controller.text.trim();
            if (trimmedText.isNotEmpty) {
              widget.onAdd(trimmedText);
              Navigator.pop(context);
            }
          },
          child: const Text('Add Task', style: TextStyle(color: AppColors.textPrimary)),
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';

class AddUrlDialog extends StatefulWidget {
  final Function(String) onAdd;

  const AddUrlDialog({Key? key, required this.onAdd}) : super(key: key);

  @override
  State<AddUrlDialog> createState() => _AddUrlDialogState();
}

class _AddUrlDialogState extends State<AddUrlDialog> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: const Color(0xFF1E1F29),
      title: const Text('Add New Download', style: TextStyle(color: Colors.white)),
      content: TextField(
        controller: _controller,
        style: const TextStyle(color: Colors.white),
        decoration: InputDecoration(
          hintText: 'Enter URL...',
          hintStyle: const TextStyle(color: Colors.white54),
          filled: true,
          fillColor: const Color(0xFF2A2C3C),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel', style: TextStyle(color: Colors.white70)),
        ),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: Colors.blueAccent,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
          onPressed: () {
            final trimmedText = _controller.text.trim();
            if (trimmedText.isNotEmpty) {
              widget.onAdd(trimmedText);
              Navigator.pop(context);
            }
          },
          child: const Text('Add Task', style: TextStyle(color: Colors.white)),
        ),
      ],
    );
  }
}

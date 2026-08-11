import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_ui/models/download_task.dart';
import 'package:flutter_ui/services/ipc_client.dart';
import 'package:flutter_ui/widgets/task_card.dart';
import 'package:flutter_ui/widgets/add_url_dialog.dart';

void main() {
  runApp(const DownloadManagerApp());
}

class DownloadManagerApp extends StatelessWidget {
  const DownloadManagerApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Download Manager',
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF15161E),
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const DownloadsPage(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class DownloadsPage extends StatefulWidget {
  const DownloadsPage({Key? key}) : super(key: key);

  @override
  State<DownloadsPage> createState() => _DownloadsPageState();
}

class _DownloadsPageState extends State<DownloadsPage> {
  final IpcClient _ipcClient = IpcClient();
  List<DownloadTask> _tasks = [];
  String _selectedCategory = 'All';
  Timer? _timer;
  
  final List<String> _categories = [
    'All', 'Downloading', 'Completed', 'Compressed', 'Documents', 'Media', 'Other'
  ];

  @override
  void initState() {
    super.initState();
    _fetchTasks();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _fetchTasks());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetchTasks() async {
    final tasks = await _ipcClient.listTasks();
    if (mounted) {
      setState(() {
        _tasks = tasks;
      });
    }
  }

  List<DownloadTask> get _filteredTasks {
    if (_selectedCategory == 'All') return _tasks;
    if (_selectedCategory == 'Downloading') {
      return _tasks.where((t) => t.status == 'DOWNLOADING').toList();
    }
    if (_selectedCategory == 'Completed') {
      return _tasks.where((t) => t.status == 'COMPLETED').toList();
    }
    return _tasks.where((t) => t.category == _selectedCategory).toList();
  }

  void _showAddDialog() {
    showDialog(
      context: context,
      builder: (context) => AddUrlDialog(
        onAdd: (url) async {
          await _ipcClient.addUrl(url);
          _fetchTasks();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Downloads', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: const Color(0xFF1E1F29),
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: Colors.blueAccent),
            onPressed: _showAddDialog,
            tooltip: 'Add Download',
          ),
          const SizedBox(width: 16),
        ],
      ),
      body: Row(
        children: [
          // Sidebar
          Container(
            width: 200,
            color: const Color(0xFF1A1C23),
            child: ListView.builder(
              itemCount: _categories.length,
              itemBuilder: (context, index) {
                final category = _categories[index];
                final isSelected = category == _selectedCategory;
                return ListTile(
                  title: Text(
                    category,
                    style: TextStyle(
                      color: isSelected ? Colors.blueAccent : Colors.white70,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                  selected: isSelected,
                  selectedTileColor: Colors.blueAccent.withOpacity(0.1),
                  onTap: () {
                    setState(() {
                      _selectedCategory = category;
                    });
                  },
                );
              },
            ),
          ),
          // Main Content
          Expanded(
            child: _filteredTasks.isEmpty
                ? const Center(
                    child: Text('No tasks found.', style: TextStyle(color: Colors.white54, fontSize: 16)),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(16),
                    itemCount: _filteredTasks.length,
                    itemBuilder: (context, index) {
                      final task = _filteredTasks[index];
                      return TaskCard(
                        task: task,
                        onPause: () => _ipcClient.pauseTask(task.id),
                        onResume: () => _ipcClient.resumeTask(task.id),
                        onCancel: () => _ipcClient.cancelTask(task.id),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

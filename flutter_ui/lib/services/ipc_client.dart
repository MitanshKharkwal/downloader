import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/download_task.dart';

class IpcClient {
  static const int _port = 47821;
  static const String _url = 'http://127.0.0.1:$_port/rpc';
  String? _token;

  Future<void> _loadToken() async {
    if (_token != null) return;
    
    final homeDir = Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'];
    if (homeDir == null) return;
    
    final tokenFile = File('$homeDir/.download_manager/ipc_token.txt');
    if (await tokenFile.exists()) {
      _token = (await tokenFile.readAsString()).trim();
    }
  }

  Future<dynamic> _callMethod(String method, [Map<String, dynamic>? args]) async {
    await _loadToken();
    if (_token == null) throw Exception("IPC Token not found");

    final response = await http.post(
      Uri.parse(_url),
      headers: {
        'Content-Type': 'application/json',
        'X-Auth-Token': _token!,
      },
      body: jsonEncode({
        'method': method,
        'args': args ?? {},
      }),
    );

    if (response.statusCode != 200) {
      throw Exception("RPC call failed with status: ${response.statusCode}");
    }

    final data = jsonDecode(response.body);
    if (data['ok'] != true) {
      throw Exception("RPC call returned error: ${data['error']}");
    }

    return data;
  }

  Future<List<DownloadTask>> listTasks() async {
    try {
      final response = await _callMethod('list_tasks');
      final tasksData = response['tasks'] as List;
      return tasksData.map((t) => DownloadTask.fromJson(t)).toList();
    } catch (e) {
      print("Error listing tasks: $e");
      return [];
    }
  }

  Future<void> addUrl(String url) async {
    await _callMethod('add_url', {'url': url});
  }

  Future<void> pauseTask(String id) async {
    await _callMethod('pause_task', {'id': id});
  }

  Future<void> resumeTask(String id) async {
    await _callMethod('resume_task', {'id': id});
  }

  Future<void> cancelTask(String id) async {
    await _callMethod('cancel_task', {'id': id});
  }
}

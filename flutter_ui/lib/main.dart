import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/library_screen.dart';
import 'theme/library_theme.dart';

void main() => runApp(const DownloadManagerApp());

class DownloadManagerApp extends StatefulWidget {
  const DownloadManagerApp({super.key});
  @override
  State<DownloadManagerApp> createState() => _DownloadManagerAppState();
}

class _DownloadManagerAppState extends State<DownloadManagerApp> {
  ThemeMode mode = ThemeMode.system;
  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((prefs) {
      if (mounted) {
        setState(
          () => mode = ThemeMode.values.firstWhere(
            (m) => m.name == prefs.getString('appearance'),
            orElse: () => ThemeMode.system,
          ),
        );
      }
    });
  }

  Future<void> changeMode(ThemeMode value) async {
    setState(() => mode = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('appearance', value.name);
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Fetchly',
    debugShowCheckedModeBanner: false,
    theme: libraryTheme(Brightness.light),
    darkTheme: libraryTheme(Brightness.dark),
    themeMode: mode,
    home: LibraryScreen(mode: mode, onModeChanged: changeMode),
  );
}

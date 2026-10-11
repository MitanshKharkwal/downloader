import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/library_screen.dart';
import 'theme/library_theme.dart';
import 'services/ipc_client.dart';

void main() => runApp(const DownloadManagerApp());

class DownloadManagerApp extends StatefulWidget {
  const DownloadManagerApp({super.key, this.client});
  final IpcClient? client;
  @override
  State<DownloadManagerApp> createState() => _DownloadManagerAppState();
}

class _DownloadManagerAppState extends State<DownloadManagerApp> {
  ThemeMode mode = ThemeMode.system;
  bool compactRows = false;
  bool reduceMotion = false;
  AccentColor accent = AccentColor.pink;
  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((prefs) {
      if (mounted) {
        setState(() {
          mode = ThemeMode.values.firstWhere(
            (m) => m.name == prefs.getString('appearance'),
            orElse: () => ThemeMode.system,
          );
          compactRows = prefs.getBool('compact_rows') ?? false;
          reduceMotion = prefs.getBool('reduce_motion') ?? false;
          accent = AccentColor.values.firstWhere(
            (value) => value.name == prefs.getString('accent_color'),
            orElse: () => AccentColor.pink,
          );
        });
      }
    });
  }

  Future<void> changeMode(ThemeMode value) async {
    setState(() => mode = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('appearance', value.name);
  }

  Future<void> changeAccent(AccentColor value) async {
    setState(() => accent = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('accent_color', value.name);
  }

  Future<void> changeCompactRows(bool value) async {
    setState(() => compactRows = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('compact_rows', value);
  }

  Future<void> changeReduceMotion(bool value) async {
    setState(() => reduceMotion = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('reduce_motion', value);
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Fetchly',
    debugShowCheckedModeBanner: false,
    theme: libraryTheme(Brightness.light, accent: accent),
    darkTheme: libraryTheme(Brightness.dark, accent: accent),
    themeAnimationDuration: reduceMotion
        ? Duration.zero
        : const Duration(milliseconds: 200),
    themeMode: mode,
    builder: (context, child) => MediaQuery(
      data: MediaQuery.of(context).copyWith(
        disableAnimations:
            reduceMotion || MediaQuery.of(context).disableAnimations,
      ),
      child: child!,
    ),
    home: LibraryScreen(
      client: widget.client,
      mode: mode,
      accent: accent,
      onAccentChanged: changeAccent,
      onModeChanged: changeMode,
      compactRows: compactRows,
      reduceMotion: reduceMotion,
      onCompactRowsChanged: changeCompactRows,
      onReduceMotionChanged: changeReduceMotion,
    ),
  );
}

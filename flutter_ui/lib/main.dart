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
  bool compactRows = false;
  bool reduceMotion = false;
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
        });
      }
    });
  }

  Future<void> changeMode(ThemeMode value) async {
    setState(() => mode = value);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('appearance', value.name);
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
    theme: libraryTheme(Brightness.light),
    darkTheme: libraryTheme(Brightness.dark),
    themeMode: mode,
    builder: (context, child) => MediaQuery(
      data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
      child: child!,
    ),
    home: LibraryScreen(
      mode: mode,
      onModeChanged: changeMode,
      compactRows: compactRows,
      reduceMotion: reduceMotion,
      onCompactRowsChanged: changeCompactRows,
      onReduceMotionChanged: changeReduceMotion,
    ),
  );
}

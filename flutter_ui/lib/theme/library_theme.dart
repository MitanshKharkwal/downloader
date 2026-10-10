import 'dart:ui';
import 'package:flutter/material.dart';

ThemeData libraryTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: const Color(0xffc83e57),
    brightness: brightness,
    primary: dark ? const Color(0xffff8193) : const Color(0xffbb2945),
    surface: dark ? const Color(0xff1c1c1e) : const Color(0xfffaf9f7),
    onSurface: dark ? const Color(0xfff1f0ee) : const Color(0xff242322),
    onSurfaceVariant: dark ? const Color(0xffaaa8a6) : const Color(0xff696562),
    outlineVariant: dark ? const Color(0xff393838) : const Color(0xffdedbd7),
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    brightness: brightness,
    fontFamily: 'General Sans',
    scaffoldBackgroundColor: scheme.surface,
    dividerColor: scheme.outlineVariant.withValues(alpha: .55),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.onSurface.withValues(alpha: .035),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
    ),
    tooltipTheme: const TooltipThemeData(
      waitDuration: Duration(milliseconds: 450),
    ),
  );
}

class Glass extends StatelessWidget {
  const Glass({super.key, required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: c.surface.withValues(alpha: .78),
            border: Border.all(color: c.outlineVariant.withValues(alpha: .3)),
          ),
          child: child,
        ),
      ),
    );
  }
}

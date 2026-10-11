import 'dart:ui';
import 'package:flutter/material.dart';

enum AccentColor {
  pink('Pink', Color(0xffbb2945), Color(0xffff8193)),
  blue('Blue', Color(0xff245ec5), Color(0xff9ebfff)),
  purple('Purple', Color(0xff7945b3), Color(0xffd2adff)),
  teal('Teal', Color(0xff08766e), Color(0xff77d9cb)),
  amber('Amber', Color(0xff8b5900), Color(0xffffcb70));

  const AccentColor(this.label, this.light, this.dark);
  final String label;
  final Color light;
  final Color dark;
}

ThemeData libraryTheme(
  Brightness brightness, {
  AccentColor accent = AccentColor.pink,
}) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: accent.light,
    brightness: brightness,
    primary: dark ? accent.dark : accent.light,
    onPrimary: dark ? const Color(0xff18181a) : Colors.white,
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
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(22),
        side: BorderSide(color: scheme.onSurface.withValues(alpha: .12)),
      ),
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
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color.alphaBlend(
                  Colors.white.withValues(alpha: .045),
                  c.surface,
                ).withValues(alpha: .87),
                c.surface.withValues(alpha: .76),
              ],
            ),
            border: Border.all(color: c.onSurface.withValues(alpha: .10)),
          ),
          child: child,
        ),
      ),
    );
  }
}

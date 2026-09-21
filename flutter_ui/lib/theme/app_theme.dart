import 'package:flutter/material.dart';

/// Central design tokens. Change the accent here and it propagates everywhere.
class AppColors {
  const AppColors._();

  static const Color background = Color(0xFF101012);
  static const Color surface = Color(0xFF1A1A1E);
  static const Color surfaceElevated = Color(0xFF222228);
  static const Color surfaceHover = Color(0xFF232328);
  static const Color surfaceActive = Color(0xFF28282D);
  static const Color border = Color(0xFF262630);
  static const Color borderStrong = Color(0xFF3A3A44);

  static const Color textPrimary = Color(0xFFE8E8EC);
  static const Color textSecondary = Color(0xFF9D9DAA);
  static const Color textMuted = Color(0xFF6B6B78);

  static const Color accent = Color(0xFF6366F1);
  static const Color accentHover = Color(0xFF818CF8);
  static const Color accentSoft = Color(0x226366F1);

  static const Color success = Color(0xFF3FBF7F);
  static const Color danger = Color(0xFFF25C5C);
  static const Color dangerSoft = Color(0x1AF25C5C);
  static const Color warning = Color(0xFFE0A83C);

  static const Color track = Color(0xFF2E2E33);
}

class AppRadius {
  const AppRadius._();

  static const BorderRadius sm = BorderRadius.all(Radius.circular(6));
  static const BorderRadius md = BorderRadius.all(Radius.circular(10));
  static const BorderRadius lg = BorderRadius.all(Radius.circular(14));
  static const BorderRadius pill = BorderRadius.all(Radius.circular(999));
}

class AppFonts {
  const AppFonts._();

  /// Use for numerical data: speeds, sizes, ETAs, percentages.
  static const String mono = 'Consolas';
}

class AppTheme {
  const AppTheme._();

  static const Duration fast = Duration(milliseconds: 140);
  static const Duration medium = Duration(milliseconds: 260);

  static TextTheme _textTheme() {
    final TextTheme base = ThemeData.dark(
      useMaterial3: true,
    ).textTheme.apply(fontFamily: 'General Sans');
    return base
        .apply(bodyColor: AppColors.textPrimary, displayColor: AppColors.textPrimary)
        .copyWith(
          displaySmall: base.displaySmall?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.8,
          ),
          headlineMedium: base.headlineMedium?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.8,
          ),
          titleMedium: base.titleMedium?.copyWith(fontWeight: FontWeight.w600, letterSpacing: -0.2),
          bodyMedium: base.bodyMedium?.copyWith(height: 1.4, fontWeight: FontWeight.w400),
          labelSmall: base.labelSmall?.copyWith(fontWeight: FontWeight.w400, letterSpacing: 0.2),
        );
  }

  static ThemeData dark() {
    final TextTheme text = _textTheme();

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: AppColors.background,
      canvasColor: AppColors.background,
      textTheme: text,
      splashFactory: NoSplash.splashFactory,
      highlightColor: Colors.transparent,
      dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1, space: 1),
      colorScheme: const ColorScheme.dark(
        primary: AppColors.accent,
        onPrimary: Colors.white,
        secondary: AppColors.accent,
        surface: AppColors.surface,
        onSurface: AppColors.textPrimary,
        error: AppColors.danger,
      ),
      iconTheme: const IconThemeData(color: AppColors.textSecondary, size: 18),
      scrollbarTheme: ScrollbarThemeData(
        thickness: const WidgetStatePropertyAll<double>(6),
        thumbColor: const WidgetStatePropertyAll<Color>(AppColors.borderStrong),
        radius: const Radius.circular(999),
      ),
      tooltipTheme: TooltipThemeData(
        waitDuration: const Duration(milliseconds: 350),
        textStyle: text.labelSmall?.copyWith(color: AppColors.textPrimary),
        decoration: BoxDecoration(
          color: AppColors.surfaceActive,
          borderRadius: AppRadius.sm,
          border: Border.all(color: AppColors.border),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        hintStyle: text.bodySmall?.copyWith(color: AppColors.textMuted),
        border: OutlineInputBorder(
          borderRadius: AppRadius.sm,
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.sm,
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.sm,
          borderSide: const BorderSide(color: AppColors.accent),
        ),
      ),
    );
  }
}

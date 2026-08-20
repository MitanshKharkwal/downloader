import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Central design tokens. Change the accent here and it propagates everywhere.
class AppColors {
  const AppColors._();

  static const Color background = Color(0xFF0E0E10);
  static const Color surface = Color(0xFF1C1C1F);
  static const Color surfaceHover = Color(0xFF232327);
  static const Color surfaceActive = Color(0xFF26262B);
  static const Color border = Color(0xFF2A2A2A);
  static const Color borderStrong = Color(0xFF35353A);

  static const Color textPrimary = Color(0xFFF4F4F5);
  static const Color textSecondary = Color(0xFFA1A1AA);
  static const Color textMuted = Color(0xFF6B6B75);

  static const Color accent = Color(0xFF5B7CFA);
  static const Color accentHover = Color(0xFF6F8CFF);
  static const Color accentSoft = Color(0x225B7CFA);

  static const Color success = Color(0xFF3FBF7F);
  static const Color danger = Color(0xFFF25C5C);
  static const Color dangerSoft = Color(0x1AF25C5C);
  static const Color warning = Color(0xFFE0A83C);

  static const Color track = Color(0xFF2E2E33);
}

class AppRadius {
  const AppRadius._();

  static const BorderRadius sm = BorderRadius.all(Radius.circular(6));
  static const BorderRadius md = BorderRadius.all(Radius.circular(8));
  static const BorderRadius lg = BorderRadius.all(Radius.circular(12));
  static const BorderRadius pill = BorderRadius.all(Radius.circular(999));
}

class AppTheme {
  const AppTheme._();

  static const Duration fast = Duration(milliseconds: 140);
  static const Duration medium = Duration(milliseconds: 260);

  static TextTheme _textTheme() {
    final TextTheme base = GoogleFonts.interTextTheme(
      ThemeData.dark(useMaterial3: true).textTheme,
    );
    return base
        .apply(
          bodyColor: AppColors.textPrimary,
          displayColor: AppColors.textPrimary,
        )
        .copyWith(
          displaySmall: base.displaySmall?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.8,
          ),
          headlineMedium: base.headlineMedium?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: -0.6,
          ),
          titleMedium: base.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
          bodyMedium: base.bodyMedium?.copyWith(height: 1.4),
          labelSmall: base.labelSmall?.copyWith(
            fontWeight: FontWeight.w500,
            letterSpacing: 0.2,
          ),
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
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: 1,
        space: 1,
      ),
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
          borderRadius: AppRadius.md,
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadius.md,
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.md,
          borderSide: const BorderSide(color: AppColors.accent),
        ),
      ),
    );
  }
}

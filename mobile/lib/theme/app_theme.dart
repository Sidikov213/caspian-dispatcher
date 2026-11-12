import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_colors.dart';
import 'app_spacing.dart';

ThemeData buildAppTheme(Brightness brightness) {
  // Не трогаем AppColors.bind — иначе после light+dark ThemeData
  // глобальная палитра залипает на тёмной и светлый UI «сливается».
  final p = AppColors.paletteFor(brightness);
  const family = 'Inter';
  final base = ThemeData(brightness: brightness).textTheme.apply(
    fontFamily: family,
    bodyColor: p.text,
    displayColor: p.text,
  );

  const noOverlay = WidgetStatePropertyAll<Color>(Colors.transparent);
  final overlayStyle = brightness == Brightness.dark
      ? SystemUiOverlayStyle.light
      : SystemUiOverlayStyle.dark;

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    fontFamily: family,
    scaffoldBackgroundColor: p.background,
    splashFactory: NoSplash.splashFactory,
    splashColor: Colors.transparent,
    highlightColor: Colors.transparent,
    hoverColor: Colors.transparent,
    focusColor: Colors.transparent,
    colorScheme: ColorScheme(
      brightness: brightness,
      primary: p.primary,
      onPrimary: Colors.white,
      secondary: p.cyan,
      onSecondary: Colors.white,
      surface: p.card,
      onSurface: p.text,
      error: p.danger,
      onError: Colors.white,
    ),
    textTheme: base.copyWith(
      headlineLarge: base.headlineLarge?.copyWith(
        fontWeight: FontWeight.w800,
        fontSize: 28,
        letterSpacing: -0.4,
        color: p.text,
      ),
      headlineMedium: base.headlineMedium?.copyWith(
        fontWeight: FontWeight.w800,
        fontSize: 22,
        color: p.text,
      ),
      titleLarge: base.titleLarge?.copyWith(
        fontWeight: FontWeight.w700,
        fontSize: 17,
        color: p.text,
      ),
      bodyLarge: base.bodyLarge?.copyWith(fontSize: 15, color: p.text),
      bodyMedium: base.bodyMedium?.copyWith(
        color: p.textSecondary,
        fontSize: 14,
      ),
      labelLarge: base.labelLarge?.copyWith(
        fontWeight: FontWeight.w700,
        fontSize: 15,
        color: p.text,
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: p.background,
      foregroundColor: p.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      systemOverlayStyle: overlayStyle,
      titleTextStyle: TextStyle(
        fontFamily: family,
        color: p.text,
        fontSize: 17,
        fontWeight: FontWeight.w700,
      ),
    ),
    cardTheme: CardThemeData(
      color: p.card,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        side: BorderSide(color: p.border),
      ),
    ),
    dividerColor: p.border,
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.field,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        borderSide: BorderSide(color: p.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        borderSide: BorderSide(color: p.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        borderSide: BorderSide(color: p.primary),
      ),
      labelStyle: TextStyle(color: p.muted),
      hintStyle: TextStyle(color: p.muted, height: 1.2),
      suffixIconConstraints: const BoxConstraints(minWidth: 44, minHeight: 44),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: p.primary,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radius),
        ),
        textStyle: const TextStyle(
          fontFamily: family,
          fontWeight: FontWeight.w700,
          fontSize: 15,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: p.text,
        minimumSize: const Size.fromHeight(AppSpacing.buttonHeight),
        side: BorderSide(color: p.borderStrong),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radius),
        ),
        textStyle: const TextStyle(
          fontFamily: family,
          fontWeight: FontWeight.w700,
          fontSize: 15,
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(
        overlayColor: noOverlay,
        foregroundColor: WidgetStatePropertyAll(p.primary),
        textStyle: const WidgetStatePropertyAll(
          TextStyle(fontFamily: family, fontWeight: FontWeight.w700),
        ),
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.primary),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: p.panel,
      contentTextStyle: TextStyle(color: p.text),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.panel,
      surfaceTintColor: Colors.transparent,
    ),
  );
}

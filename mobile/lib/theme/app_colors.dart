import 'package:flutter/material.dart';

/// Minimal V2. Светлая/тёмная через [bind] (MaterialApp.builder).
/// Важно: [buildAppTheme] не должен оставлять bind на «чужой» яркости —
/// иначе на светлом фоне остаётся светлый текст и всё сливается.
abstract final class AppColors {
  static bool _dark = true;

  static void bind(Brightness brightness) {
    _dark = brightness != Brightness.light;
  }

  static bool get isDark => _dark;

  /// Палитра без мутации глобального bind — для сборки ThemeData.
  static AppPalette paletteFor(Brightness brightness) =>
      brightness == Brightness.dark ? AppPalette.dark : AppPalette.light;

  static Color get background => _p.background;
  static Color get panel => _p.panel;
  static Color get card => _p.card;
  static Color get field => _p.field;
  static Color get border => _p.border;
  static Color get borderStrong => _p.borderStrong;
  static Color get primary => _p.primary;
  static Color get cyan => _p.cyan;
  static Color get text => _p.text;
  static Color get textSecondary => _p.textSecondary;
  static Color get muted => _p.muted;
  static Color get danger => _p.danger;
  static Color get warning => _p.warning;
  static Color get success => _p.success;
  static Color get transit => _p.transit;
  static Color get dangerBg => _p.dangerBg;
  static Color get warningBg => _p.warningBg;
  static Color get successBg => _p.successBg;
  static Color get infoBg => _p.infoBg;
  static Color get neutralBg => _p.neutralBg;
  static Color get skeleton => _p.skeleton;
  static Color get overlay => _p.overlay;

  static AppPalette get _p => _dark ? AppPalette.dark : AppPalette.light;

  static Color statusFg(CargoStatusTone tone) => _p.statusFg(tone);
  static Color statusBg(CargoStatusTone tone) => _p.statusBg(tone);
}

class AppPalette {
  const AppPalette({
    required this.background,
    required this.panel,
    required this.card,
    required this.field,
    required this.border,
    required this.borderStrong,
    required this.primary,
    required this.cyan,
    required this.text,
    required this.textSecondary,
    required this.muted,
    required this.danger,
    required this.warning,
    required this.success,
    required this.transit,
    required this.dangerBg,
    required this.warningBg,
    required this.successBg,
    required this.infoBg,
    required this.neutralBg,
    required this.skeleton,
    required this.overlay,
    required this.deliveredAccent,
  });

  final Color background;
  final Color panel;
  final Color card;
  final Color field;
  final Color border;
  final Color borderStrong;
  final Color primary;
  final Color cyan;
  final Color text;
  final Color textSecondary;
  final Color muted;
  final Color danger;
  final Color warning;
  final Color success;
  final Color transit;
  final Color dangerBg;
  final Color warningBg;
  final Color successBg;
  final Color infoBg;
  final Color neutralBg;
  final Color skeleton;
  final Color overlay;
  final Color deliveredAccent;

  static const dark = AppPalette(
    background: Color(0xFF0B1220),
    panel: Color(0xFF131C2E),
    card: Color(0xFF172338),
    field: Color(0xFF101B2D),
    border: Color(0xFF24304A),
    borderStrong: Color(0xFF30425C),
    primary: Color(0xFF2F80ED),
    cyan: Color(0xFF73D9EE),
    text: Color(0xFFE6EDF7),
    textSecondary: Color(0xFFCBD5E1),
    muted: Color(0xFF8A97AD),
    danger: Color(0xFFEF4444),
    warning: Color(0xFFF59E0B),
    success: Color(0xFF22C55E),
    transit: Color(0xFF3B82F6),
    dangerBg: Color(0x26EF4444),
    warningBg: Color(0x26F59E0B),
    successBg: Color(0x2622C55E),
    infoBg: Color(0x262F80ED),
    neutralBg: Color(0x268A97AD),
    skeleton: Color(0xFF1A2438),
    overlay: Color(0x990B1220),
    deliveredAccent: Color(0xFF69E6A0),
  );

  /// Светлая: белый фон, контрастный текст и границы.
  static const light = AppPalette(
    background: Color(0xFFFFFFFF),
    panel: Color(0xFFFFFFFF),
    card: Color(0xFFFFFFFF),
    field: Color(0xFFF1F5F9),
    border: Color(0xFFD0D8E4),
    borderStrong: Color(0xFF94A3B8),
    primary: Color(0xFF1D4ED8),
    cyan: Color(0xFF0F766E),
    text: Color(0xFF0B1220),
    textSecondary: Color(0xFF334155),
    muted: Color(0xFF64748B),
    danger: Color(0xFFB91C1C),
    warning: Color(0xFFB45309),
    success: Color(0xFF15803D),
    transit: Color(0xFF1D4ED8),
    dangerBg: Color(0xFFFEE2E2),
    warningBg: Color(0xFFFEF3C7),
    successBg: Color(0xFFDCFCE7),
    infoBg: Color(0xFFDBEAFE),
    neutralBg: Color(0xFFE2E8F0),
    skeleton: Color(0xFFD8E0EB),
    overlay: Color(0x660B1220),
    deliveredAccent: Color(0xFF15803D),
  );

  Color statusFg(CargoStatusTone tone) => switch (tone) {
    CargoStatusTone.planned => muted,
    CargoStatusTone.inTransit => transit,
    CargoStatusTone.atRisk => danger,
    CargoStatusTone.rerouted => success,
    CargoStatusTone.delivered => deliveredAccent,
  };

  Color statusBg(CargoStatusTone tone) => switch (tone) {
    CargoStatusTone.planned => neutralBg,
    CargoStatusTone.inTransit => transit.withValues(alpha: 0.12),
    CargoStatusTone.atRisk => dangerBg,
    CargoStatusTone.rerouted => successBg,
    CargoStatusTone.delivered => neutralBg,
  };
}

enum CargoStatusTone { planned, inTransit, atRisk, rerouted, delivered }

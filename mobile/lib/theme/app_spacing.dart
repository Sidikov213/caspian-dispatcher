import 'package:flutter/material.dart';

abstract final class AppSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 18.0;
  static const xl = 24.0;
  static const xxl = 32.0;

  static const page = EdgeInsets.fromLTRB(18, 8, 18, 24);
  static const radius = 12.0;
  static const radiusSm = 8.0;
  static const buttonHeight = 48.0;

  /// Отступ страницы с учётом системной панели (Android gesture / кнопки).
  static EdgeInsets pageOf(BuildContext context, {bool safeBottom = true}) {
    if (!safeBottom) return page;
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    if (bottom <= 0) return page;
    return page.copyWith(bottom: page.bottom + bottom);
  }
}

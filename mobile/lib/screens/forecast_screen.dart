import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';

/// 05 — Прогноз срыва стыковки (без выбора маршрута).
class ForecastScreen extends StatelessWidget {
  const ForecastScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final cargo = app.byId(cargoId);
    if (cargo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Прогноз')),
        body: const EmptyStateView(
          icon: Icons.search_off_rounded,
          title: 'Груз не найден',
          subtitle: 'Обновите список грузов.',
        ),
      );
    }

    final decision = app.decisionFor(cargo);
    final pct = cargo.missProbability.clamp(0.0, 1.0);

    return Scaffold(
      appBar: AppBar(title: Text('Прогноз · ${cargo.number}')),
      body: ListView(
        padding: AppSpacing.page,
        children: [
          AppCard(
            padding: const EdgeInsets.fromLTRB(18, 24, 18, 20),
            child: Column(
              children: [
                SizedBox(
                  width: 160,
                  height: 160,
                  child: CustomPaint(
                    painter: _RingPainter(progress: pct),
                    child: Center(
                      child: Text(
                        '${(pct * 100).round()}%',
                        style: TextStyle(
                          color: AppColors.text,
                          fontSize: 36,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.8,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  'Вероятность срыва стыковки',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Причины'),
                const SizedBox(height: 10),
                if (cargo.riskFactors.isEmpty)
                  Text(
                    'Факторы риска не переданы сервером',
                    style: TextStyle(color: AppColors.textSecondary),
                  )
                else
                  for (final f in cargo.riskFactors) ...[
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            f.label,
                            style: TextStyle(
                              color: AppColors.text,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Text(
                          '+${f.impactHours.round()} ч',
                          style: TextStyle(
                            color: AppColors.cyan,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                  ],
              ],
            ),
          ),
          if (cargo.probabilityDrivers.isNotEmpty) ...[
            const SizedBox(height: 12),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionLabel('Вклад в вероятность'),
                  const SizedBox(height: 6),
                  Text(
                    'Признаки модели (п. п. вероятности срыва)',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 10),
                  for (final d in cargo.probabilityDrivers) ...[
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            d.label,
                            style: TextStyle(
                              color: AppColors.text,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Text(
                          '${d.impactPp >= 0 ? '+' : ''}${d.impactPp.toStringAsFixed(1).replaceAll('.', ',')} п.п.',
                          style: TextStyle(
                            color: AppColors.primary,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                  ],
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Последствия'),
                const SizedBox(height: 10),
                Text(
                  cargo.departureShiftH == null
                      ? 'Сдвиг отправления не указан'
                      : 'Отправление на ${cargo.departureShiftH!.round()} ч позже планового рейса',
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    height: 1.35,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  cargo.arrivalDelayH == null
                      ? 'Задержка при отмене рейса не указана'
                      : 'Если рейс отменят: прибытие +${cargo.arrivalDelayH!.round()} ч',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 14,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            borderColor: decision.waiting
                ? AppColors.warning
                : AppColors.success,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Статус решения'),
                const SizedBox(height: 8),
                Text(
                  decision.summary ?? 'Нет активного решения по этому грузу',
                  style: TextStyle(
                    color: decision.waiting
                        ? AppColors.warning
                        : AppColors.text,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    height: 1.35,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Маршрут выбирает логист на сайте или в Телеграме.',
                  style: TextStyle(color: AppColors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final r = size.width / 2 - 8;
    final bg = Paint()
      ..color = AppColors.border
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.round;
    final fg = Paint()
      ..color = progress >= 0.7 ? AppColors.danger : AppColors.primary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(c, r, bg);
    canvas.drawArc(
      Rect.fromCircle(center: c, radius: r),
      -math.pi / 2,
      2 * math.pi * progress,
      false,
      fg,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter oldDelegate) =>
      oldDelegate.progress != progress;
}

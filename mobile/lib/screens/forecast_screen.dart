import 'package:flutter/material.dart';

import '../api/mappers.dart';
import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';

/// Прогноз срыва стыковки — в стиле цифрового двойника / сайта.
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
        body: app.showDataPlaceholders
            ? const ForecastLoadingSkeleton()
            : const EmptyStateView(
                icon: Icons.search_off_rounded,
                title: 'Груз не найден',
                subtitle: 'Обновите список грузов.',
              ),
      );
    }

    if (app.showDataPlaceholders) {
      return Scaffold(
        appBar: AppBar(title: Text('Прогноз · ${cargo.number}')),
        body: const ForecastLoadingSkeleton(),
      );
    }

    final decision = app.decisionFor(cargo);
    final level = cargo.riskLevel;
    final (fg, bg, border) = switch (level) {
      'high' => (
          AppColors.danger,
          AppColors.dangerBg,
          AppColors.danger.withValues(alpha: 0.35),
        ),
      'medium' => (
          AppColors.warning,
          AppColors.warningBg,
          AppColors.warning.withValues(alpha: 0.35),
        ),
      _ => (
          AppColors.success,
          AppColors.successBg,
          AppColors.success.withValues(alpha: 0.3),
        ),
    };
    final shift = cargo.departureShiftH ?? 0;
    final maxImpact = cargo.riskFactors.isEmpty
        ? 1.0
        : cargo.riskFactors
            .map((f) => f.impactHours)
            .fold<double>(1, (a, b) => a > b ? a : b);
    final maxDriver = cargo.probabilityDrivers.isEmpty
        ? 1.0
        : cargo.probabilityDrivers
            .map((d) => d.impactPp.abs())
            .fold<double>(1, (a, b) => a > b ? a : b);

    return Scaffold(
      appBar: AppBar(title: Text('Прогноз · ${cargo.number}')),
      body: ListView(
        padding: AppSpacing.pageOf(context),
        children: [
          Text(
            'Предиктор стыковки',
            style: TextStyle(
              color: AppColors.cyan,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.55,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            cargo.displayName,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${cargo.weight} · ${cargo.origin} → ${cargo.destination}',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
          ),
          const SizedBox(height: 16),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(AppSpacing.radius),
              border: Border.all(color: border),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'ВЕРОЯТНОСТЬ СРЫВА СТЫКОВКИ',
                  style: TextStyle(
                    color: fg,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.5,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      flex: 5,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${cargo.riskPercent}%',
                            style: TextStyle(
                              color: fg,
                              fontSize: 44,
                              fontWeight: FontWeight.w800,
                              height: 1.0,
                              letterSpacing: -1.2,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            cargo.hasFerry
                                ? 'Вероятность опоздать на паром'
                                : 'Риск задержки на границе',
                            style: TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 12,
                              height: 1.3,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      flex: 4,
                      child: Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              fmtHoursDelta(shift),
                              style: TextStyle(
                                color: AppColors.text,
                                fontSize: 26,
                                fontWeight: FontWeight.w800,
                                height: 1.1,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              shift > 0
                                  ? 'позже планового рейса'
                                  : 'по расписанию',
                              style: TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                if ((cargo.arrivalDelayH ?? 0) > 0) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Если рейс отменят: прибытие ${fmtHoursDelta(cargo.arrivalDelayH!)}',
                    style: TextStyle(
                      color: fg,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      height: 1.3,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Причины'),
                const SizedBox(height: 6),
                Text(
                  'Вклад факторов в задержку',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 12),
                if (cargo.riskFactors.isEmpty)
                  Text(
                    'Факторы риска не переданы сервером',
                    style: TextStyle(color: AppColors.textSecondary),
                  )
                else
                  for (var i = 0; i < cargo.riskFactors.length; i++) ...[
                    _ImpactRow(
                      label: cargo.riskFactors[i].label,
                      value: fmtHoursDelta(cargo.riskFactors[i].impactHours),
                      ratio: (cargo.riskFactors[i].impactHours / maxImpact)
                          .clamp(0.04, 1.0),
                      barColor: i == 0 && level == 'high'
                          ? AppColors.danger
                          : AppColors.warning,
                      valueColor: AppColors.text,
                    ),
                    if (i != cargo.riskFactors.length - 1)
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
                    'Признаки модели, п. п. вероятности срыва',
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 12),
                  for (var i = 0; i < cargo.probabilityDrivers.length; i++) ...[
                    Builder(
                      builder: (_) {
                        final d = cargo.probabilityDrivers[i];
                        final pos = d.impactPp >= 0;
                        final raw = d.impactPp.abs() % 1 == 0
                            ? d.impactPp.abs().toInt().toString()
                            : d.impactPp
                                .abs()
                                .toStringAsFixed(1)
                                .replaceAll('.', ',');
                        return _ImpactRow(
                          label: d.label,
                          value: '${pos ? '+' : '−'}$raw п.п.',
                          ratio: (d.impactPp.abs() / maxDriver)
                              .clamp(0.04, 1.0),
                          barColor: pos ? AppColors.danger : AppColors.success,
                          valueColor:
                              pos ? AppColors.danger : AppColors.success,
                        );
                      },
                    ),
                    if (i != cargo.probabilityDrivers.length - 1)
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
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _MetricTile(
                        label: 'К плану',
                        value: fmtHoursDelta(shift),
                        valueColor: shift > 0
                            ? AppColors.warning
                            : AppColors.text,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _MetricTile(
                        label: 'При отмене',
                        value: cargo.arrivalDelayH == null
                            ? '—'
                            : fmtHoursDelta(cargo.arrivalDelayH!),
                        valueColor: (cargo.arrivalDelayH ?? 0) > 0
                            ? AppColors.danger
                            : AppColors.text,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Text(
                  shift > 0
                      ? 'Отправление смещается на ${shift.round()} ч относительно планового рейса.'
                      : 'Отправление пока по расписанию.',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _DecisionCard(decision: decision),
        ],
      ),
    );
  }
}

class _ImpactRow extends StatelessWidget {
  const _ImpactRow({
    required this.label,
    required this.value,
    required this.ratio,
    required this.barColor,
    required this.valueColor,
  });

  final String label;
  final String value;
  final double ratio;
  final Color barColor;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              value,
              style: TextStyle(
                color: valueColor,
                fontSize: 13,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(99),
          child: SizedBox(
            height: 5,
            child: Stack(
              children: [
                Positioned.fill(
                  child: ColoredBox(
                    color: AppColors.border.withValues(alpha: 0.75),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: ratio,
                  child: ColoredBox(color: barColor),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    required this.valueColor,
  });

  final String label;
  final String value;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.field,
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              color: valueColor,
              fontSize: 18,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.2,
            ),
          ),
        ],
      ),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.decision});

  final DispatcherDecision decision;

  @override
  Widget build(BuildContext context) {
    final waiting = decision.waiting;
    final fg = waiting ? AppColors.warning : AppColors.success;
    final bg = waiting ? AppColors.warningBg : AppColors.successBg;
    final border = fg.withValues(alpha: 0.3);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        border: Border.all(color: border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'СТАТУС РЕШЕНИЯ',
            style: TextStyle(
              color: fg,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            decision.summary ?? 'Нет активного решения по этому грузу',
            style: TextStyle(
              color: waiting ? fg : AppColors.text,
              fontSize: 15,
              fontWeight: FontWeight.w800,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            waiting
                ? 'Маршрут выбирает логист на сайте или в Телеграме.'
                : 'Решение уже зафиксировано в системе.',
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
              height: 1.35,
            ),
          ),
        ],
      ),
    );
  }
}

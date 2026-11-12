import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../api/mappers.dart';
import '../models/cargo.dart';
import '../services/camera_permission.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import 'corridor_screen.dart';
import 'document_capture_screen.dart';
import 'forecast_screen.dart';
import 'pass_screen.dart';

class CargoDetailScreen extends StatelessWidget {
  const CargoDetailScreen({super.key, required this.cargoId});

  final String cargoId;

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final cargo = app.byId(cargoId);

    if (cargo == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Груз')),
        body: app.showDataPlaceholders
            ? const TwinLoadingSkeleton()
            : EmptyStateView(
                icon: Icons.search_off_rounded,
                title: 'Груз не найден',
                subtitle: app.errorMessage ?? 'Обновите данные с сервера.',
                actionLabel: 'Обновить',
                onAction: () => app.refresh(forceLoading: true),
              ),
      );
    }

    if (app.showDataPlaceholders) {
      return Scaffold(
        appBar: AppBar(title: const Text('Груз')),
        body: const TwinLoadingSkeleton(),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Груз'),
      ),
      body: ListView(
        padding: AppSpacing.pageOf(context),
        children: [
          Text(
            'Цифровой двойник',
            style: TextStyle(
              color: AppColors.cyan,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            cargo.displayName,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 26,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.4,
              height: 1.15,
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${cargo.weight} · ${cargo.cargoTypeLabel}',
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                  ),
                ),
              ),
              StatusPill(status: cargo.displayStatus, compact: true),
            ],
          ),
          if (cargo.showRouteChangedBadge || cargo.routeChanged) ...[
            const SizedBox(height: 10),
            SoftBadge(
              label: 'Маршрут изменён',
              background: AppColors.warningBg,
              foreground: AppColors.warning,
            ),
          ],
          if (cargo.missProbability > 0 || cargo.riskFactors.isNotEmpty) ...[
            const SizedBox(height: 16),
            _RiskCard(cargo: cargo),
          ],
          if (cargo.stages.isNotEmpty) ...[
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Этапы маршрута',
                    style: TextStyle(
                      color: AppColors.text,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                Text(
                  'План / прогноз',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            for (var i = 0; i < cargo.stages.length; i++)
              _TwinStageRow(
                stage: cargo.stages[i],
                isLast: i == cargo.stages.length - 1,
              ),
          ],
          if (cargo.totalCo2Kg > 0) ...[
            const SizedBox(height: 16),
            _Co2Card(cargo: cargo),
          ],
          const SizedBox(height: 12),
          _PassCard(
            cargo: cargo,
            onOpen: () => _openPass(context, cargo),
          ),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ForecastScreen(cargoId: cargo.id),
                ),
              );
            },
            icon: const Icon(Icons.alt_route_rounded, size: 18),
            label: const Text('Альтернативные маршруты'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => CorridorScreen(cargoId: cargo.id),
                ),
              );
            },
            child: const Text('Цифровой коридор'),
          ),
          if (cargo.passStatus == PassStatus.awaitingReissue) ...[
            const SizedBox(height: 10),
            OutlinedButton(
              onPressed: () async {
                final err = await app.retryPass(cargo.id);
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(err ?? 'Пропуск переоформлен')),
                );
              },
              child: const Text('Повторить переоформление'),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _openPass(BuildContext context, Cargo cargo) async {
    final hasPass = cargo.passStatus != PassStatus.none;
    if (hasPass) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => PassScreen(cargoId: cargo.id)),
      );
      return;
    }
    final allowed = await ensureCameraPermission(context);
    if (!allowed || !context.mounted) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DocumentCaptureScreen(cargoId: cargo.id),
      ),
    );
  }
}

class _RiskCard extends StatelessWidget {
  const _RiskCard({required this.cargo});

  final Cargo cargo;

  @override
  Widget build(BuildContext context) {
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
            'РИСК СРЫВА СТЫКОВКИ',
            style: TextStyle(
              color: fg,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 6),
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
                        fontSize: 40,
                        fontWeight: FontWeight.w800,
                        height: 1.05,
                        letterSpacing: -1,
                      ),
                    ),
                    const SizedBox(height: 4),
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
                  padding: const EdgeInsets.only(top: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        fmtHoursDelta(shift),
                        style: TextStyle(
                          color: AppColors.text,
                          fontSize: 24,
                          fontWeight: FontWeight.w800,
                          height: 1.1,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        shift > 0 ? 'позже планового рейса' : 'по расписанию',
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
            const SizedBox(height: 8),
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
          if (cargo.riskFactors.isNotEmpty) ...[
            const SizedBox(height: 10),
            for (var i = 0; i < cargo.riskFactors.length; i++) ...[
              _FactorBar(
                label: cargo.riskFactors[i].label,
                hours: cargo.riskFactors[i].impactHours,
                maxHours: maxImpact,
                barColor: i == 0 && level == 'high'
                    ? AppColors.danger
                    : AppColors.warning,
              ),
              if (i != cargo.riskFactors.length - 1) const SizedBox(height: 6),
            ],
          ],
        ],
      ),
    );
  }
}

class _FactorBar extends StatelessWidget {
  const _FactorBar({
    required this.label,
    required this.hours,
    required this.maxHours,
    required this.barColor,
  });

  final String label;
  final double hours;
  final double maxHours;
  final Color barColor;

  @override
  Widget build(BuildContext context) {
    final ratio = (hours / maxHours).clamp(0.04, 1.0);
    return Row(
      children: [
        Expanded(
          flex: 5,
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        Expanded(
          flex: 4,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: SizedBox(
                height: 4,
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: ColoredBox(
                        color: AppColors.border.withValues(alpha: 0.7),
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
          ),
        ),
        SizedBox(
          width: 42,
          child: Text(
            fmtHoursDelta(hours),
            textAlign: TextAlign.right,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }
}

class _TwinStageRow extends StatelessWidget {
  const _TwinStageRow({required this.stage, required this.isLast});

  final RouteStage stage;
  final bool isLast;

  IconData get _icon => switch (stage.mode) {
        'sea' => Icons.directions_boat_outlined,
        'road' => Icons.local_shipping_outlined,
        _ => Icons.train_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final danger = stage.warning;
    final iconBg = danger ? AppColors.dangerBg : AppColors.infoBg;
    final iconFg = danger ? AppColors.danger : AppColors.primary;

    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 12),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Column(
              children: [
                Container(
                  width: 30,
                  height: 30,
                  decoration: BoxDecoration(
                    color: iconBg,
                    borderRadius: BorderRadius.circular(7),
                  ),
                  child: Icon(_icon, size: 16, color: iconFg),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 1,
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      color: AppColors.borderStrong,
                    ),
                  ),
              ],
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Expanded(
                        child: Text(
                          stage.title,
                          style: TextStyle(
                            color: AppColors.text,
                            fontSize: 14,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          stage.timeLine.isNotEmpty
                              ? stage.timeLine
                              : 'План ${stage.planned}',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                            color: danger
                                ? AppColors.danger
                                : AppColors.muted,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    stage.subtitle,
                    style: TextStyle(
                      color: AppColors.muted,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Co2Card extends StatelessWidget {
  const _Co2Card({required this.cargo});

  final Cargo cargo;

  @override
  Widget build(BuildContext context) {
    final parts = <({String label, double value, Color color})>[
      if (cargo.co2RailKg > 0)
        (label: 'Ж/д', value: cargo.co2RailKg, color: AppColors.primary),
      if (cargo.co2SeaKg > 0)
        (label: 'Море', value: cargo.co2SeaKg, color: AppColors.cyan),
      if (cargo.co2RoadKg > 0)
        (label: 'Авто', value: cargo.co2RoadKg, color: AppColors.success),
    ];
    final sum = parts.fold<double>(0, (a, b) => a + b.value);
    final total = cargo.totalCo2Kg > 0 ? cargo.totalCo2Kg : sum;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.eco_outlined, size: 18, color: AppColors.success),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Выбросы CO₂',
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              Text(
                '${total.round()} кг',
                style: TextStyle(
                  color: AppColors.text,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          if (parts.isNotEmpty && sum > 0) ...[
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: SizedBox(
                height: 5,
                child: Row(
                  children: [
                    for (var i = 0; i < parts.length; i++) ...[
                      if (i > 0) const SizedBox(width: 3),
                      Expanded(
                        flex: (parts[i].value / sum * 1000).round().clamp(1, 1000),
                        child: ColoredBox(color: parts[i].color),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              [
                for (var i = 0; i < parts.length; i++)
                  '${parts[i].label} ${parts[i].value.round()}${i == parts.length - 1 ? ' кг' : ''}',
              ].join(' · '),
              style: TextStyle(
                color: AppColors.muted,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PassCard extends StatelessWidget {
  const _PassCard({required this.cargo, required this.onOpen});

  final Cargo cargo;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final hasPass = cargo.passStatus != PassStatus.none;
    late final String title;
    late final String sub;
    late final Color titleColor;

    if (cargo.passStatus == PassStatus.awaitingReissue) {
      title = 'Пропуск ожидает переоформления';
      sub = cargo.passPort != null
          ? 'Действует старый: ${cargo.passPort}'
          : 'Маршрут изменён';
      titleColor = AppColors.warning;
    } else if (!hasPass) {
      title = 'Пропуск не оформлен';
      sub = 'Нужен снимок инвойса в приложении';
      titleColor = AppColors.muted;
    } else {
      title = 'Пропуск оформлен';
      sub = cargo.passPort != null ? 'порт ${cargo.passPort}' : 'Открыть пропуск';
      titleColor = AppColors.text;
    }

    final token = cargo.passToken;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onOpen,
        borderRadius: BorderRadius.circular(AppSpacing.radius),
        child: Ink(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(AppSpacing.radius),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: AppColors.field,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  Icons.description_outlined,
                  size: 18,
                  color: AppColors.muted,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: titleColor,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      sub,
                      style: TextStyle(
                        color: AppColors.muted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              if (token != null &&
                  token.isNotEmpty &&
                  cargo.passStatus != PassStatus.none) ...[
                const SizedBox(width: 10),
                Container(
                  width: 48,
                  height: 48,
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: QrImageView(
                    data: token,
                    version: QrVersions.auto,
                    padding: EdgeInsets.zero,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

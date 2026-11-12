import 'package:flutter/material.dart';

import '../models/cargo.dart';
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
        body: EmptyStateView(
          icon: Icons.search_off_rounded,
          title: 'Груз не найден',
          subtitle: app.errorMessage ?? 'Обновите данные с сервера.',
          actionLabel: 'Обновить',
          onAction: () => app.refresh(forceLoading: true),
        ),
      );
    }

    final hasPass = cargo.passStatus != PassStatus.none;
    final waves = app.overview?.waves ?? const <WavePort>[];

    return Scaffold(
      appBar: AppBar(title: Text(cargo.displayName)),
      body: ListView(
        padding: AppSpacing.page,
        children: [
          Text(
            cargo.title,
            style: TextStyle(
              color: AppColors.text,
              fontSize: 26,
              fontWeight: FontWeight.w800,
              letterSpacing: -0.4,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${cargo.weight} · ${cargo.origin} → ${cargo.destination}',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              StatusPill(status: cargo.displayStatus),
              if (cargo.showRouteChangedBadge || cargo.routeChanged)
                SoftBadge(
                  label: 'Маршрут изменён',
                  background: AppColors.warningBg,
                  foreground: AppColors.warning,
                ),
            ],
          ),
          const SizedBox(height: 16),
          AppCard(
            onTap: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => ForecastScreen(cargoId: cargo.id),
                ),
              );
            },
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: SectionLabel('Прогноз прибытия')),
                    Text(
                      'Открыть',
                      style: TextStyle(
                        color: AppColors.primary,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  cargo.arrival,
                  style: TextStyle(
                    color: AppColors.text,
                    fontSize: 30,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.6,
                  ),
                ),
                if (cargo.riskPercent > 0) ...[
                  const SizedBox(height: 10),
                  Text(
                    '${cargo.riskPercent}% риск срыва стыковки',
                    style: TextStyle(
                      color: cargo.displayStatus == CargoStatus.atRisk
                          ? AppColors.danger
                          : AppColors.textSecondary,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (waves.isNotEmpty) ...[
            const SizedBox(height: 12),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionLabel('Волна в портах'),
                  const SizedBox(height: 10),
                  for (final w in waves) ...[
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            w.name,
                            style: TextStyle(
                              color: AppColors.text,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        SoftBadge(
                          label: w.heightLabel,
                          background: AppColors.infoBg,
                          foreground: AppColors.primary,
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                  ],
                ],
              ),
            ),
          ],
          if (cargo.stages.isNotEmpty) ...[
            const SizedBox(height: 12),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionLabel('Этапы перевозки'),
                  const SizedBox(height: 10),
                  for (var i = 0; i < cargo.stages.length; i++) ...[
                    _StageRow(stage: cargo.stages[i]),
                    if (i != cargo.stages.length - 1)
                      Padding(
                        padding: EdgeInsets.only(left: 11, top: 2, bottom: 2),
                        child: SizedBox(
                          height: 14,
                          child: VerticalDivider(
                            width: 2,
                            thickness: 2,
                            color: AppColors.cyan,
                          ),
                        ),
                      ),
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
                Row(
                  children: [
                    const Expanded(child: SectionLabel('Пропуск')),
                    if (hasPass) PassStatusPill(status: cargo.passStatus),
                  ],
                ),
                const SizedBox(height: 10),
                _kv('Пункт', cargo.passPort ?? cargo.nextPoint),
                const SizedBox(height: 6),
                _kv('Срок', cargo.passValidUntil ?? '-'),
                const SizedBox(height: 6),
                _kv(
                  'Состояние',
                  hasPass ? cargo.passStatus.label : 'Ещё не оформлен',
                ),
                const SizedBox(height: 8),
                Text(
                  'Внутренний демонстрационный пропуск сервиса, не официальный портовый документ.',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontSize: 12,
                    height: 1.35,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
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
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () {
              if (hasPass) {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => PassScreen(cargoId: cargo.id),
                  ),
                );
              } else {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => DocumentCaptureScreen(cargoId: cargo.id),
                  ),
                );
              }
            },
            child: Text(hasPass ? 'Показать QR' : 'Оформить пропуск'),
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

  Widget _kv(String k, String v) {
    return Row(
      children: [
        SizedBox(
          width: 100,
          child: Text(k, style: TextStyle(color: AppColors.muted)),
        ),
        Expanded(
          child: Text(
            v,
            style: TextStyle(
              color: AppColors.text,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}

class _StageRow extends StatelessWidget {
  const _StageRow({required this.stage});

  final RouteStage stage;

  @override
  Widget build(BuildContext context) {
    final color = stage.warning
        ? AppColors.danger
        : stage.current
        ? AppColors.primary
        : stage.done
        ? AppColors.success
        : AppColors.muted;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.18),
            border: Border.all(color: color),
          ),
          child: Icon(
            stage.done ? Icons.check : Icons.circle,
            size: stage.done ? 12 : 6,
            color: color,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                stage.title,
                style: TextStyle(
                  color: AppColors.text,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(
                stage.subtitle,
                style: TextStyle(color: AppColors.muted, fontSize: 12),
              ),
              Text(
                'План ${stage.planned} · прогноз ${stage.forecast}',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

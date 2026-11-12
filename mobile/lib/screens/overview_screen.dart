import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/last_event_card.dart';
import '../widgets/logo_mark.dart';
import 'cargo_detail_screen.dart';
import 'settings_screen.dart';

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final stats = app.overview;

    if (app.loadState == AppLoadState.loading && stats == null) {
      return const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          BrandHeader(title: 'Обзор'),
          Expanded(child: LoadingListSkeleton()),
        ],
      );
    }

    if (app.loadState == AppLoadState.error && stats == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const BrandHeader(title: 'Обзор'),
          Expanded(
            child: ErrorStateView(
              message: app.errorMessage ?? 'Ошибка',
              onRetry: () => app.refresh(forceLoading: true),
            ),
          ),
        ],
      );
    }

    if (stats == null) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        BrandHeader(
          title: 'Обзор',
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (app.refreshing)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              IconButton(
                tooltip: 'Настройки',
                splashColor: Colors.transparent,
                highlightColor: Colors.transparent,
                hoverColor: Colors.transparent,
                focusColor: Colors.transparent,
                style: IconButton.styleFrom(
                  overlayColor: Colors.transparent,
                  highlightColor: Colors.transparent,
                  hoverColor: Colors.transparent,
                  focusColor: Colors.transparent,
                ),
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => const SettingsScreen()),
                  );
                },
                icon: Icon(
                  Icons.settings_outlined,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            padding: AppSpacing.page,
            children: [
              Text(
                'Актуальная ситуация по перевозкам',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: AppCard(
                      onTap: () =>
                          app.setHomeTab(1, cargoFilter: CargoListFilter.all),
                      child: MetricBlock(
                        value: '${stats.shipmentsTotal}',
                        label: 'Всего грузов',
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: AppCard(
                      onTap: () => app.setHomeTab(
                        1,
                        cargoFilter: CargoListFilter.atRisk,
                      ),
                      child: MetricBlock(
                        value: '${stats.atRisk}',
                        label: 'Под риском',
                        accent: AppColors.danger,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionLabel('Расчётная экономия'),
                    const SizedBox(height: 10),
                    Text(
                      stats.economyRub,
                      style: TextStyle(
                        color: AppColors.success,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      stats.economyCargoHours,
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (stats.economyCo2Pct != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        stats.economyCo2Pct!,
                        style: TextStyle(
                          color: AppColors.cyan,
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
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
                    Row(
                      children: [
                        const Expanded(child: SectionLabel('Волна в портах')),
                        if (stats.weatherStale)
                          SoftBadge(
                            label: 'Устарело',
                            background: AppColors.warningBg,
                            foreground: AppColors.warning,
                          ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    for (final w in stats.waves) ...[
                      _wave(w.name, w.heightLabel),
                      const SizedBox(height: 8),
                    ],
                    Text(
                      '${stats.weatherSource} · ${stats.weatherUpdatedLabel}',
                      style: TextStyle(color: AppColors.muted, fontSize: 12),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              LastEventCard(
                card: stats.lastAlertCard,
                fallbackTitle: stats.lastAlertTitle,
                fallbackBody: stats.lastAlertBody,
                fallbackDecision: stats.decisionNote,
                onTap: stats.lastAlertCargoId == null
                    ? null
                    : () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => CargoDetailScreen(
                              cargoId: stats.lastAlertCargoId!,
                            ),
                          ),
                        );
                      },
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _wave(String port, String height) {
    return Row(
      children: [
        Expanded(
          child: Text(
            port,
            style: TextStyle(
              color: AppColors.text,
              fontWeight: FontWeight.w600,
              fontSize: 14,
            ),
          ),
        ),
        SoftBadge(
          label: height,
          background: AppColors.infoBg,
          foreground: AppColors.primary,
        ),
      ],
    );
  }
}

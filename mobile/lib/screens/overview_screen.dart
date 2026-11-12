import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/economy_summary_card.dart';
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
    final header = BrandHeader(
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
          _settingsButton(context),
        ],
      ),
    );

    if (app.loadState == AppLoadState.error && stats == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header,
          Expanded(
            child: ErrorStateView(
              message: app.errorMessage ?? 'Ошибка',
              onRetry: () => app.refresh(forceLoading: true),
            ),
          ),
        ],
      );
    }

    if (app.showDataPlaceholders || stats == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header,
          const Expanded(child: OverviewLoadingSkeleton()),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        header,
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
              EconomySummaryCard(
                rub: stats.economyRub,
                cargoHours: stats.economyCargoHours,
                co2Pct: stats.economyCo2Pct,
              ),
              const SizedBox(height: 12),
              _PortWavesCard(
                waves: stats.waves,
                weatherStale: stats.weatherStale,
                footer: '${stats.weatherSource} · ${stats.weatherUpdatedLabel}',
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

  Widget _settingsButton(BuildContext context) {
    return IconButton(
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
      icon: Icon(Icons.settings_outlined, color: AppColors.textSecondary),
    );
  }

}

class _PortWavesCard extends StatefulWidget {
  const _PortWavesCard({
    required this.waves,
    required this.weatherStale,
    required this.footer,
  });

  final List<WavePort> waves;
  final bool weatherStale;
  final String footer;

  static const _collapsedCount = 4;

  @override
  State<_PortWavesCard> createState() => _PortWavesCardState();
}

class _PortWavesCardState extends State<_PortWavesCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final waves = widget.waves;
    final canToggle = waves.length > _PortWavesCard._collapsedCount;
    final visible = !canToggle || _expanded
        ? waves
        : waves.take(_PortWavesCard._collapsedCount).toList(growable: false);
    final hidden = canToggle
        ? waves.length - _PortWavesCard._collapsedCount
        : 0;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: SectionLabel('Волна в портах')),
              if (widget.weatherStale)
                SoftBadge(
                  label: 'Устарело',
                  background: AppColors.warningBg,
                  foreground: AppColors.warning,
                ),
            ],
          ),
          const SizedBox(height: 10),
          for (var i = 0; i < visible.length; i++) ...[
            _waveRow(visible[i].name, visible[i].heightLabel),
            if (i != visible.length - 1) const SizedBox(height: 8),
          ],
          if (canToggle) ...[
            const SizedBox(height: 4),
            TextButton(
              onPressed: () => setState(() => _expanded = !_expanded),
              style: TextButton.styleFrom(
                foregroundColor: AppColors.primary,
                padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    _expanded
                        ? 'Свернуть'
                        : 'Ещё $hidden ${_portWord(hidden)}',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Icon(
                    _expanded
                        ? Icons.keyboard_arrow_up_rounded
                        : Icons.keyboard_arrow_down_rounded,
                    size: 18,
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            widget.footer,
            style: TextStyle(color: AppColors.muted, fontSize: 12),
          ),
        ],
      ),
    );
  }

  String _portWord(int n) {
    final mod10 = n % 10;
    final mod100 = n % 100;
    if (mod10 == 1 && mod100 != 11) return 'порт';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
      return 'порта';
    }
    return 'портов';
  }

  Widget _waveRow(String port, String height) {
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

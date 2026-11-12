import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/filter_chips.dart';
import '../widgets/logo_mark.dart';
import 'cargo_detail_screen.dart';

class MyCargosScreen extends StatelessWidget {
  const MyCargosScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final filter = app.cargoListFilter;
    final list = app.filteredCargos;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const BrandHeader(title: 'Мои грузы'),
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 4, 18, 10),
          child: Text(
            filter == CargoListFilter.all
                ? 'Данные с сервера · ${list.length}'
                : '${filter.label}: ${list.length}',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
          ),
        ),
        FilterChipBar<CargoListFilter>(
          value: filter,
          onChanged: app.setCargoListFilter,
          items: [
            for (final f in CargoListFilter.values)
              (f, '${f.label} (${app.countCargos(f)})'),
          ],
        ),
        const SizedBox(height: 10),
        Expanded(child: _body(context, app, list)),
      ],
    );
  }

  Widget _body(BuildContext context, AppController app, List<Cargo> list) {
    if (app.showDataPlaceholders) {
      return const CargoListLoadingSkeleton();
    }
    if (app.loadState == AppLoadState.error && app.cargos.isEmpty) {
      return ErrorStateView(
        message: app.errorMessage ?? 'Ошибка',
        onRetry: () => app.refresh(forceLoading: true),
      );
    }
    if (list.isEmpty) {
      return const EmptyStateView(
        icon: Icons.inventory_2_outlined,
        title: 'Грузов нет',
        subtitle: 'На сервере пока нет назначенных перевозок.',
      );
    }
    return ListView.separated(
      padding: AppSpacing.page,
      itemCount: list.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, i) {
        final c = list[i];
        return AppCard(
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => CargoDetailScreen(cargoId: c.id),
              ),
            );
          },
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      c.displayName,
                      style: TextStyle(
                        color: AppColors.text,
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  StatusPill(status: c.displayStatus, compact: true),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                '${c.weight} · ${c.origin} → ${c.destination}',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
              ),
              if (c.riskPercent > 0) ...[
                const SizedBox(height: 8),
                Text(
                  'Риск срыва стыковки ${c.riskPercent}%',
                  style: TextStyle(
                    color: c.displayStatus == CargoStatus.atRisk
                        ? AppColors.danger
                        : AppColors.muted,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

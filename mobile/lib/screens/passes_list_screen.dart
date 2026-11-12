import 'package:flutter/material.dart';

import '../models/cargo.dart';
import '../state/app_controller.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../widgets/app_chrome.dart';
import '../widgets/filter_chips.dart';
import '../widgets/logo_mark.dart';
import 'pass_screen.dart';

class PassesListScreen extends StatelessWidget {
  const PassesListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final filter = app.passListFilter;
    final items = app.filteredStoredPasses;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const BrandHeader(title: 'Пропуска'),
        Padding(
          padding: const EdgeInsets.fromLTRB(18, 4, 18, 12),
          child: Text(
            filter == PassListFilter.all
                ? 'История · ${items.length}'
                : '${filter.label}: ${items.length}',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 14),
          ),
        ),
        FilterChipBar<PassListFilter>(
          value: filter,
          onChanged: app.setPassListFilter,
          items: [
            for (final f in PassListFilter.values)
              (f, '${f.label} (${app.countStoredPasses(f)})'),
          ],
        ),
        const SizedBox(height: 10),
        Expanded(
          child: app.showDataPlaceholders
              ? const PassesListLoadingSkeleton()
              : items.isEmpty
              ? EmptyStateView(
                  icon: Icons.badge_outlined,
                  title: 'Пропусков пока нет',
                  subtitle:
                      'История с сервера и копии на устройстве. Старый пропуск не затирается.',
                  actionLabel: app.loadState == AppLoadState.error
                      ? 'Повторить загрузку'
                      : null,
                  onAction: app.loadState == AppLoadState.error
                      ? () => app.refresh(forceLoading: true)
                      : null,
                )
              : ListView.separated(
                  padding: AppSpacing.page,
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (context, i) {
                    final p = items[i];
                    return AppCard(
                      onTap: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => PassScreen(
                              cargoId: p.shipmentId,
                              storedPassId: p.id,
                            ),
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
                                  '${p.cargoNumber} ${p.cargoTitle}'.trim(),
                                  style: TextStyle(
                                    color: AppColors.text,
                                    fontWeight: FontWeight.w800,
                                    fontSize: 15,
                                  ),
                                ),
                              ),
                              PassStatusPill(status: p.status),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '${p.checkpointLabel} · до ${p.validUntilLabel}',
                            style: TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 13,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            p.id,
                            style: TextStyle(
                              color: AppColors.muted,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}
